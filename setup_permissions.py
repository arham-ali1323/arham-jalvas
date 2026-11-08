"""
MARK LIV Permission Setup Script

This script helps grant necessary Windows permissions to MARK LIV.
Run as Administrator for full functionality.
"""
import os
import sys
import ctypes
import subprocess
from pathlib import Path


def is_admin():
    """Check if script is running as administrator."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """Re-run script as administrator."""
    script = os.path.abspath(sys.argv[0])
    params = ' '.join([script] + sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )


def grant_microphone_permission():
    """Grant microphone access to MARK LIV."""
    print("🎤 Granting microphone permission...")
    try:
        # Enable microphone access via registry
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone",
            0,
            winreg.KEY_WRITE
        )
        winreg.SetValueEx(key, "NonPackaged", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        print("✅ Microphone permission granted")
        return True
    except Exception as e:
        print(f"⚠️  Could not grant microphone permission: {e}")
        print("   Please manually enable in: Settings → Privacy → Microphone")
        return False


def grant_camera_permission():
    """Grant camera access to MARK LIV."""
    print("📷 Granting camera permission...")
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam",
            0,
            winreg.KEY_WRITE
        )
        winreg.SetValueEx(key, "NonPackaged", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        print("✅ Camera permission granted")
        return True
    except Exception as e:
        print(f"⚠️  Could not grant camera permission: {e}")
        print("   Please manually enable in: Settings → Privacy → Camera")
        return False


def add_firewall_exception():
    """Add MARK LIV to Windows Firewall exceptions."""
    print("🔥 Adding firewall exception...")
    try:
        # Get the current executable path
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = sys.executable  # Python interpreter

        cmd = [
            'netsh', 'advfirewall', 'firewall', 'add', 'rule',
            f'name="MARK LIV"',
            f'dir=in',
            f'action=allow',
            f'program="{exe_path}"',
            f'enable=yes'
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print("✅ Firewall exception added")
        return True
    except Exception as e:
        print(f"⚠️  Could not add firewall exception: {e}")
        print("   Please manually add in: Windows Defender Firewall → Allow an app")
        return False


def disable_ransomware_protection_for_app():
    """Add MARK LIV to controlled folder access allowlist."""
    print("🛡️  Adding to ransomware protection allowlist...")
    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = sys.executable

        cmd = [
            'powershell', '-Command',
            f'Add-MpPreference -ControlledFolderAccessAllowedApplications "{exe_path}"'
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print("✅ Added to ransomware protection allowlist")
        return True
    except Exception as e:
        print(f"⚠️  Could not add to allowlist: {e}")
        print("   Please manually add in: Windows Security → Ransomware protection → Controlled folder access")
        return False


def grant_python_permissions():
    """Grant execution permissions to Python."""
    print("🐍 Granting Python execution permissions...")
    try:
        # Add to Windows Defender exclusions
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        cmd = [
            'powershell', '-Command',
            f'Add-MpPreference -ExclusionPath "{app_dir}"'
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ Added {app_dir} to Windows Defender exclusions")
        return True
    except Exception as e:
        print(f"⚠️  Could not add to exclusions: {e}")
        return False


def check_permissions():
    """Check current permission status."""
    print("\n📋 Checking current permissions...")
    print("-" * 50)

    # Check admin status
    admin = is_admin()
    print(f"Administrator: {'✅ Yes' if admin else '❌ No'}")

    # Check microphone
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        mics = [d for d in devices if d['max_input_channels'] > 0]
        print(f"Microphone access: {'✅ Available' if mics else '❌ No microphones'}")
    except:
        print("Microphone access: ❌ Not available")

    # Check firewall
    try:
        result = subprocess.run(
            ['netsh', 'advfirewall', 'firewall', 'show', 'rule', 'name="MARK LIV"'],
            capture_output=True,
            text=True
        )
        if "MARK LIV" in result.stdout:
            print("Firewall exception: ✅ Configured")
        else:
            print("Firewall exception: ❌ Not configured")
    except:
        print("Firewall exception: ❓ Could not check")

    print("-" * 50)


def interactive_setup():
    """Interactive permission setup."""
    print("""
╔════════════════════════════════════════════════════════════╗
║          MARK LIV Permission Setup                      ║
╚════════════════════════════════════════════════════════════╝

This script will grant MARK LIV the permissions it needs.
Please review each permission before granting.

WARNING: Only grant permissions you are comfortable with.
    """)

    if not is_admin():
        print("⚠️  This script requires administrator privileges.")
        response = input("Restart as administrator? (y/n): ")
        if response.lower() == 'y':
            run_as_admin()
            sys.exit()
        else:
            print("❌ Cannot grant permissions without administrator access.")
            sys.exit(1)

    check_permissions()

    print("\nAvailable permissions to grant:")
    print("1. Microphone access (required for voice input)")
    print("2. Camera access (required for vision)")
    print("3. Firewall exception (required for network access)")
    print("4. Ransomware protection allowlist (required for file access)")
    print("5. Windows Defender exclusion (recommended)")
    print("6. Grant all permissions")
    print("0. Exit")

    choice = input("\nSelect permissions to grant (1-6, or 0 to exit): ")

    if choice == '1':
        grant_microphone_permission()
    elif choice == '2':
        grant_camera_permission()
    elif choice == '3':
        add_firewall_exception()
    elif choice == '4':
        disable_ransomware_protection_for_app()
    elif choice == '5':
        grant_python_permissions()
    elif choice == '6':
        print("\n🚀 Granting all permissions...")
        grant_microphone_permission()
        grant_camera_permission()
        add_firewall_exception()
        disable_ransomware_protection_for_app()
        grant_python_permissions()
    elif choice == '0':
        print("Exiting...")
        sys.exit(0)
    else:
        print("Invalid choice")

    print("\n" + "=" * 50)
    print("✅ Permission setup complete!")
    print("=" * 50)


def auto_setup():
    """Non-interactive automatic setup (grant all)."""
    if not is_admin():
        print("⚠️  Restarting as administrator...")
        run_as_admin()
        sys.exit()

    print("🚀 Auto-granting all permissions...")
    grant_microphone_permission()
    grant_camera_permission()
    add_firewall_exception()
    disable_ransomware_protection_for_app()
    grant_python_permissions()
    print("\n✅ All permissions granted!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        auto_setup()
    else:
        interactive_setup()
