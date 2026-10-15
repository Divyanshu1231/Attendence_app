from app.security import hash_password, verify_password

def test_password_hash_round_trip():
    encoded = hash_password("Safe-password-123")
    assert verify_password("Safe-password-123", encoded)
    assert not verify_password("wrong-password", encoded)
