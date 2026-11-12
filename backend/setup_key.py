"""Save a key once in the OS vault, without sending a validation/API request."""
from getpass import getpass
from .credentials import save_key


def main():
    value = getpass("Gemini key (hidden, stored locally without an API call): ").strip().rstrip("\\")
    if not 20 <= len(value) <= 512 or any(character.isspace() for character in value):
        raise SystemExit("Enter the key alone, without spaces or a trailing backslash.")
    save_key(value)
    print("Key saved in the OS credential store. It was not used for an API request. Indu will load it on its next backend launch.")


if __name__ == "__main__":
    main()
