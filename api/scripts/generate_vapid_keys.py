from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import base64

def generate_vapid_keys():
    # Use instance of SECP256R1, fixing the error user saw with class
    private_key = ec.generate_private_key(ec.SECP256R1()) 
    
    # Public Key
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    # Base64 URL Safe
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')
    
    # Private Key (Integer -> Bytes -> Base64)
    private_val = private_key.private_numbers().private_value
    private_bytes = private_val.to_bytes(32, byteorder='big')
    private_b64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')

    print("\nSUCCESS! Add these to your .env file:\n")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print(f"VAPID_CLAIM_EMAIL=mailto:admin@example.com")
    print("\n-------------------------------------------")

if __name__ == "__main__":
    generate_vapid_keys()
