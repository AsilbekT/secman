"""
secman.py
Module to manage secrets in a project

This module provides a set of functions to manage secrets in a project.
Reads the command line arguments and performs the requested action.
It reads the contents of the file and line per line:
  - ignores comments and empty lines
  - in other cases, processes the variable name and value
The module uses the cryptography library for encryption and decryption.
The encryption algorithm used is the Fernet symmetric encryption algorithm,
and a valid Fernet key is required to encrypt and decrypt the secrets.

Command line arguments:
    -h, --help: Show help
    -l, --list: List all secrets
    -e, --encrypt: Encrypt all secrets in a file
    -d, --decrypt: Decrypt all secrets in a file
    -f, --file: Set the target file to manage (default: project_secrets.py)
    -k, --key: provides you a valid encryption key (valid Fernet key)
    -m, --master: Set the MASTER key value (env var name)
    -c, --convert: Convert secrets in a file to a different MASTER key

The target file should have the following format:
- A comment block at the top with information about the file
  This comment block should be set by "#" characters at the beginning of the line
- A variable named MASTER_KEY with the name of the environment variable which
  holds the master key
- Then the rest of the lines in the file should be for the secrets.
  Each secret must have two lines of the kind:
    <SECRET_NAME> = ""
    <SECRET_NAME>_ENCRYPTED = "<ENCRYPTED_VALUE>"    #<MASTER_KEY>, <DATETIME>, <SIGNATURE>

    , where:
    - <SECRET_NAME> must be a valid Python variable name, and should be an empty string
    - <ENCRYPTED_VALUE> is the encrypted value of the applicable secret
    - <MASTER_KEY> is the name of the environment variable which holds the master key used to encrypt the secret
    - <DATETIME> is the date and time when the secret was encrypted (format: YYYY-MM-DD HH:MM:SS)
    - <SIGNATURE> is the signature of the encrypted value, calculated using the next sequence:
        1. Concatenate the <ENCRYPTED_VALUE>, <DATETIME> and <MASTER_KEY> values
        2. Calculate the SHA256 hash of the concatenated value
        3. Encode the hash as a base64 string
        4. The result is the <SIGNATURE> value

References:
  - Approaches to storing secrets:
    https://12factor.net/config
  - https://beaglesecurity.com/blog/article/secrets-in-python.html
  - https://blog.gitguardian.com/how-to-handle-secrets-in-python/


Author: EduardoRE
Date: 2024-06-18
"""

# TODO: Test the master_key as Fernet key at the very beginning and remove try/except blocks for Encryption/Decryption
# TODO: Add a function to validate the Fernet key
# TODO: Implement the convert_secrets function
# TODO: Implement the verification of the signature when converting secrets

import importlib.util
import sys
import hashlib
import os
import argparse
import base64
import re
import datetime
import textwrap
from crypto_utils import decrypt_value, encrypt_value, generate_key


HEADER_DISCLAIMER = (
    "# Generated by secman.py. Do not edit manually, unless you know what you are doing"
)

HEADER = """
#  SECRET KEYS file
#
#  Generated by secman.py
#  Do not edit this file manually, unless you know what you are doing
#  Remember to keep copies of your secrets in a safe place
#
#  Note:
#    lines not processed by secman.py will be those starting with "#"
#    or empty lines
#
"""


def load_config_file(module_name, filename):
    try:
        spec = importlib.util.spec_from_file_location(module_name, filename)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config
    except Exception as e:
        print("Error: Could not properly import the configuration file")
        print(f"Error: {e}")
        sys.exit(1)


def get_master_key(env_variable):
    """
    Get the MASTER key value from the environment variable
    """
    if env_variable:
        master_key = os.getenv(env_variable)
        if master_key:
            return master_key
        else:
            print(
                f"Error: {env_variable} is empty. Set the key value in the variable first"
            )
            sys.exit(1)
    else:
        print(
            f"Error: f{env_variable} is empty. Set name of the environment variable which holds the master key"
        )
        sys.exit(1)


def list_secrets(file_path):
    """
    List all secrets in the target file
    """
    with open(file_path, "r") as file:
        lines = file.readlines()
        for line in lines:
            if line.startswith("#") or line.strip() == "":
                continue
            secret_name = line.split("=")[0].strip()
            print(secret_name)


def delete_secret(file_path, secret_name):
    """
    Delete a secret from the target file
    """
    with open(file_path, "r") as file:
        lines = file.readlines()
    with open(file_path, "w") as file:
        for line in lines:
            if line.startswith("#") or line.strip() == "":
                file.write(line)
                continue
            if line.split("=")[0].strip() == secret_name:
                continue
            file.write(line)


def encrypt_secrets(file_path, master_key_env, master_key=None):
    """
    Encrypt all secrets in the target file
    """
    count_encrypted = 0
    if not master_key:
        master_key = os.getenv(master_key_env)
    lines = open(file_path, "r").readlines()
    encrypted_secrets = set()
    # Build a list of currently existing <name>_ENCRYPTED values in the file
    encrypted_pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)_ENCRYPTED\s*=")
    for line in lines:
        match = encrypted_pattern.match(line)
        if match:
            encrypted_secrets.add(match.group(1))
    with open(file_path, "w") as file:
        if lines[0].strip() != HEADER_DISCLAIMER:
            file.write(HEADER_DISCLAIMER + "\n")
        for line in lines:
            if line.startswith("#") or line.strip() == "" or "=" not in line:
                file.write(line)
                continue
            secret_name, secret_value = line.split("=", 1)
            secret_name = secret_name.strip()  # Remove starting or ending whitespaces
            secret_value = secret_value.strip().strip('"')
            if secret_name == "MASTER_KEY_ENV":
                file.write(line)
            elif secret_name.strip().endswith("_ENCRYPTED"):
                file.write(line)
            elif secret_name in encrypted_secrets:
                file.write(f'{secret_name} = ""\n')
                if secret_value:
                    print(
                        f"Skipping {secret_name}: already encrypted in the file.\n        To re-encrypt it, delete the line and run the script again"
                    )
            else:
                try:
                    encrypted_value = encrypt_value(secret_value, master_key)
                except Exception as e:
                    print(
                        f"Error encrypting. Ensure you are providing a valid Fernet key."
                    )
                    sys.exit(1)
                current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                signature = base64.b64encode(
                    hashlib.sha512(
                        f"{master_key}".encode()
                    ).digest()
                ).decode()
                encrypted_line = f'{secret_name} = ""\n{secret_name}_ENCRYPTED = "{encrypted_value}"    #{master_key_env},{signature[-8:]},{current_datetime}\n'
                file.write(encrypted_line)
                count_encrypted += 1
                print(
                    f"Encrypted {secret_name}. Original unencrypted value has been removed from the file."
                )
    return count_encrypted


def decrypt_secrets(file_path, master_key_env, master_key=None):
    """
    Decrypt all secrets in the target file
    """
    # Ensure that the master_key is provided
    master_key = os.getenv(master_key_env)
    if not master_key:
        print(f"Error: {master_key_env} environment variable is not set")
        return
    # Build a list of existing encrypted secrets (<name>_ENCRYPTED) in the file
    encrypted_secrets = set()
    with open(file_path, "r") as file:
        lines = file.readlines()
    encrypted_pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*_ENCRYPTED)\s*=")
    for line in lines:
        match = encrypted_pattern.match(line)
        if match:
            encrypted_secrets.add(match.group(1))
    # Process the file:
    # - If the line is a comment or empty, write it as is
    # - If the line is a secret, decrypt it and write the decrypted value
    # - other lines are removed
    with open(file_path, "w") as file:
        for line in lines:
            # Preserve comments and empty lines
            if line.startswith("#") or line.strip() == "":
                file.write(line)
                continue
            # Identify and Process the secret lines
            match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*["\'](.*?)["\']', line)
            if match:
                secret_name = match.group(1)
                encrypted_value = match.group(2)
                # If the secret_name value found does not end with _ENCRYPTED and
                # the secret_name+"_ENCRYPTED" is not in the encrypted_secrets set then
                # write the line as is else skip the line
                if secret_name == "MASTER_KEY_ENV":
                    file.write(line)
                elif not secret_name.endswith("_ENCRYPTED") and f"{secret_name}_ENCRYPTED" not in encrypted_secrets:
                    file.write(f'{secret_name} = "{encrypted_value}"\n')
                elif secret_name.endswith("_ENCRYPTED"):
                    decrypted_value = decrypt_value(encrypted_value, master_key)
                    decrypted_line = f'{secret_name[:-10]} = "{decrypted_value}"\n'
                    file.write(decrypted_line)


def convert_secrets(file_path, old_master_key, new_master_key):
    """
    Convert secrets in the target file to a different MASTER key
    """
    print("NOT IMPLEMENTED YET")
    sys.exit(0)
    with open(file_path, "r") as file:
        lines = file.readlines()
    with open(file_path, "w") as file:
        file.write(lines[0])  # Preserve the comment block
        file.write(f"MASTER_KEY = '{new_master_key}'\n")
        for line in lines[2:]:
            if line.startswith("#") or line.strip() == "":
                file.write(line)
                continue
            secret_name = line.split("=")[0].strip()
            encrypted_value = line.split("=")[1].strip().strip('"')
            decrypted_value = decrypt_value(encrypted_value, old_master_key)
            encrypted_value = encrypt_value(decrypted_value, new_master_key)
            converted_line = (
                f"{secret_name} = ''\n{secret_name}_ENCRYPTED = '{encrypted_value}'\n"
            )
            file.write(converted_line)


def set_master_key(file_path, master_key_env):
    """
    Set the MASTER_KEY_ENV value in the target file
    """
    with open(file_path, "r") as file:
        lines = file.readlines()
    with open(file_path, "w") as file:
        for line in lines:
            if re.match(r"^\s*MASTER_KEY_ENV\s*=", line):
                file.write(f'MASTER_KEY_ENV = "{master_key_env}"\n')
            else:
                file.write(line)


# Function to encrypt a message
# Function to decrypt a message
# def encrypt_value(value, master_key):
#    """
#    Encrypt a value using the Fernet symmetric encryption algorithm
#    """
#    salt = os.urandom(16)  # A random salt for key derivation
#    key = hashlib.pbkdf2_hmac("sha256", master_key.encode(), salt, 100000, dklen=32)
#    fernet = Fernet(base64.urlsafe_b64encode(key))
#    encrypted_value = fernet.encrypt(value.encode()).decode()
#    return encrypted_value

# from passlib.hash import sha256_crypt
#
# def encrypt_value(value, master_key):
#    """
#    Encrypt a value using the symmetric encryption algorithm from passlib
#    """
#    encrypted_value = sha256_crypt.using(rounds=100000, salt_size=16).hash(value + master_key)
#    return encrypted_value
#
# def decrypt_value(value, master_key):
#    """
#    Decrypt a value using the Fernet symmetric encryption algorithm
#    """
#    fernet = Fernet(base64.urlsafe_b64encode(pbkdf2_sha256.hash(master_key.encode())))
#    decrypted_value = fernet.decrypt(value.encode()).decode()
#    return decrypted_value
#


def main():
    """
    Main function to handle command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Module to manage secrets in a project",
        epilog="""
        Notes:
          Empty strings as secret values are not encrypted.
          After encrypting secrets, the original variables are
          left in the file, with empty strings as values.
        """
    )
    parser.add_argument(
        "-m",
        "--master-key-env",
        metavar="MASTER_KEY_ENV_NAME",
        help="The name of the environment variable name to be set as the master key in the secrets file",
    )
    parser.add_argument("-l", "--list", action="store_true", help="List all secrets")
    parser.add_argument(
        "-e", "--encrypt", action="store_true", help="Encrypt all secrets in a file"
    )
    parser.add_argument(
        "-d", "--decrypt", action="store_true", help="Decrypt all secrets in a file"
    )
    parser.add_argument(
        "-c",
        "--convert",
        metavar=("OLD_MASTER_KEY", "NEW_MASTER_KEY"),
        nargs=2,
        help="Convert secrets in a file to a different MASTER key - NOT IMPLEMENTED YET",
    )
    parser.add_argument(
        "-f",
        "--file",
        metavar="FILE_PATH",
        default="project_secrets.py",
        help="Set the target file to manage (default: project_secrets.py)",
    )
    parser.add_argument(
        "-k",
        "--key",
        action="store_true",
        help="Print a valid encryption key (valid Fernet key)",
    )

    args = parser.parse_args()
    psecrets = load_config_file("psecret", args.file)

    if args.master_key_env:
        set_master_key(args.file, args.master_key_env)
    elif args.key:
        generate_key()
    elif args.list:
        list_secrets(args.file)
    elif args.encrypt:
        master_key = get_master_key(psecrets.MASTER_KEY_ENV)
        print("Encrypting secrets ...")
        print(
            "NOTE: Empty string as secrets are not encrypted."
        )
        n = encrypt_secrets(args.file, psecrets.MASTER_KEY_ENV)
        print(f"Done. {n} secrets encrypted.")
    elif args.decrypt:
        master_key = get_master_key(psecrets.MASTER_KEY_ENV)
        decrypt_secrets(args.file, psecrets.MASTER_KEY_ENV, master_key)
    elif args.convert:
        master_key = get_master_key(psecrets.MASTER_KEY_ENV)
        convert_secrets(args.file, args.convert[0], args.convert[1])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
