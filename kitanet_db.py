import psycopg
import ssl
import os
import kitanet_helper
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv

load_dotenv(".env")

SSH_HOST = os.getenv("SSH_HOST")
SSH_USER = os.getenv("SSH_USER")
SSH_PKEY_PATH = os.getenv("SSH_PKEY_PATH")
RDS_HOST = os.getenv("RDS_HOST")
rds_port = os.getenv("RDS_PORT")
if (returnTuple := kitanet_helper.succeeds(int, rds_port))[0]:
    rds_port = returnTuple[1]
else:
    rds_port = None
RDS_PORT = rds_port
RDS_CA_PATH = os.getenv("RDS_CA_PATH")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

class DB:
    def __init__(self, sshHost: str | None = SSH_HOST, sshUser: str | None = SSH_USER, sshPKeyPath: str | None = SSH_PKEY_PATH, sshPKey: str | None = None, rdsHost: str | None = RDS_HOST, rdsPort: int | None = RDS_PORT, rdsCAPath: str | None = RDS_CA_PATH, rdsCA: str | None = None, dbName: str | None = None, dbUser: str | None = None, dbPassword: str | None = None):
        if (None in [sshHost, sshUser, rdsHost, rdsPort]):
            raise ValueError("Missing connection parameters")
        self._sshHost = sshHost
        self._sshUser = sshUser
        self._sshPKeyPath = sshPKeyPath
        self._sshPKey = sshPKey
        self._rdsHost = rdsHost
        self._rdsPort = rdsPort
        self._rdsCAPath = rdsCAPath
        self._rdsCA = rdsCA
        self._dbName = dbName
        self._dbUser = dbUser
        self._dbPassword = dbPassword
        self._tunnel = SSHTunnelForwarder((self._sshHost, 22), ssh_username = self._sshUser, ssh_pkey = self._sshPKey if self._sshPKey != None else self._sshPKeyPath, remote_bind_address = (self._rdsHost, self._rdsPort))
        self._tunnel.start()

        if self._rdsCA != None:
            sslContext = ssl.create_default_context()
            sslContext.load_verify_locations(cadata = self._rdsCA)
            sslContext.check_hostname = True
            sslContext.verify_mode = ssl.CERT_REQUIRED
            try:
                self._connection = psycopg.connect(host = "127.0.0.1", port = self._tunnel.local_bind_port, dbname = self._dbName, user = self._dbUser, password = self._dbPassword, ssl_context = sslContext)
            except Exception:
                self._tunnel.stop()
                raise
        else:
            try:
                self._connection = psycopg.connect(host = "127.0.0.1", port = self._tunnel.local_bind_port, dbname = self._dbName, user = self._dbUser, password = self._dbPassword, sslmode = "verify-ca", sslrootcert = self._rdsCAPath)
            except Exception:
                self._tunnel.stop()
                raise

    def execute(self, command: str | None = None):
        # print(f"executing {command}")
        operation = command.split(" ")[0]
        if (command != None):
            with self._connection.cursor() as cursor:
                cursor.execute(command)
                if (operation.lower() == "select"):
                    results = cursor.fetchall()
                    return results
                else:
                    self._connection.commit()
                
    def close(self):
        self._connection.close()

def main():
    db = DB(dbName = DB_NAME, dbUser = DB_USER, dbPassword = DB_PASSWORD)
    while ((command := input("Execute command: ")) != "exit"):
        while (command[-1] != ";"):
            command += input("> ")
        result = db.execute(command)
        for item in result:
            print(item)
    db.close()

if __name__ == "__main__":
    main()