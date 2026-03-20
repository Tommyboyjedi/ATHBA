# CSRF Protection

The frontend automatically attaches the CSRF token to all HTMX requests.

## How it works

- On page load `static/js/base.js` reads the token from `<meta name="csrf-token">`.
- If a token is found it registers a global `htmx:configRequest` listener that adds an `X-CSRFToken` header to each HTMX request.
- If the meta tag is missing, the script does nothing.

## Next steps

When server endpoints are updated to require CSRF validation, existing `csrf_exempt` decorators can be removed safely.
