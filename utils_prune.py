# TODO remove repetitive records

'''
def is_duplicate(hex_code, now, baro_rate):
    if hex_code not in last_seen:
        return False
    last_time, last_vr_sign = last_seen[hex_code]
    if abs((now - last_time).total_seconds()) < 300:  # < 5 minutes
        if (baro_rate >= 0 and last_vr_sign >= 0) or (baro_rate < 0 and last_vr_sign < 0):
            return True
    return False
'''