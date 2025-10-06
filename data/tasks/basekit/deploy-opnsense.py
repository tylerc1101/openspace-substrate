import subprocess

def run_install_script():
    try:
        # Run the shell command with sudo privileges
        result = subprocess.run(
            ["sudo", "/data/images/base-kit-1.0.1/scripts/install_opnsense.sh"],
            check=True,          # Raises CalledProcessError if the command fails
            text=True,            # Decode output as text (not bytes)
            capture_output=True   # Capture stdout and stderr
        )

        print("✅ Script executed successfully!")
        print("Output:")
        print(result.stdout)

    except subprocess.CalledProcessError as e:
        print("❌ Script failed with error code:", e.returncode)
        print("Error output:")
        print(e.stderr)
    except FileNotFoundError:
        print("❌ install_opnsense.sh not found or not executable.")
    except Exception as e:
        print("⚠️ Unexpected error:", e)

if __name__ == "__main__":
    run_install_script()
