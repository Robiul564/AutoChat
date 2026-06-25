from fastapi import Request


def public_base_url_from_request(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        proto = forwarded_proto or request.url.scheme
        return f"{proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")
