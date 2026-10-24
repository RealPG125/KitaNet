def succeeds(func, *args, **kwargs):
    try:
        return True, func(*args, **kwargs)
    except Exception:
        return False, -1

def find_port(start: int = 55555, end: int = 65535, pool: list[int] | None = None) -> int:
    if (type(pool) == list and len(pool) != 0):
        for i in range(end - start + 1):
            if ((start + i) not in pool):
                return start + i
    else: 
        return start