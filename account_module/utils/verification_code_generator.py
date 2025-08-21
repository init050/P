import random
import string

class VerificationCodeGenerator:
    @staticmethod
    def generate_6_digit_code():
        # Generate 6-digit numeric code for old email verification
        return ''.join(random.choices(string.digits, k=6))