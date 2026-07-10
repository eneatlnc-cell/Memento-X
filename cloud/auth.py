"""Re-export from cloud.account.auth for backward compatibility."""
from cloud.account.auth import (
    get_current_user,
    decode_access_token,
    create_access_token,
    hash_password,
    verify_password,
    register_user,
    authenticate_user,
)