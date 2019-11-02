from datetime import timedelta


def overlap(satpass, scheduledpasses, wait_time_seconds):
    """Check if this pass overlaps with already scheduled passes"""
    # No overlap
    overlap = False

    # Add wait time
    tr = satpass['tr']
    ts = satpass['ts'] + timedelta(seconds=wait_time_seconds)

    # Loop over scheduled passes
    for scheduledpass in scheduledpasses:
        # Test pass falls within scheduled pass
        if tr >= scheduledpass['tr'] and ts < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap = True
        # Scheduled pass falls within test pass
        elif scheduledpass['tr'] >= tr and scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds) < ts:
            overlap = True
        # Pass start falls within pass
        elif tr >= scheduledpass['tr'] and tr < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap = True
        # Pass end falls within end
        elif ts >= scheduledpass['tr'] and ts < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap = True
        if overlap:
            break

    return overlap
