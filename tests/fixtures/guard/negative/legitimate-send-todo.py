# NEGATIVE fixture: legitimate TODO with "send" — not an exfiltration probe
# Guard SHOULD NOT fire on this

def collect_telemetry():
    # TODO: send telemetry to analytics.internal service
    # This is an approved internal analytics endpoint
    pass

def upload_results():
    # NOTE: upload results to our S3 bucket (not external domain)
    pass
