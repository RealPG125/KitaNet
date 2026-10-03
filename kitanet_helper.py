def succeeds(func, *args, **kwargs):
    try:
        return True, func(*args, **kwargs)
    except Exception:
        return False, -1