def succeeds(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        return True
    except Exception:
        return False