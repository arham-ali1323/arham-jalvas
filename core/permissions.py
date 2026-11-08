"""
MARK LIV Permission Checker

Checks if MARK LIV has the necessary permissions to run properly.
Can be called from main.py to show missing permissions to the user.
"""
import os
import sys
import ctypes
import subprocess
from pathlib import Path


class PermissionChecker:
    """Check and report MARK LIV permissions."""

    @staticmethod
    def is_admin():
        """Check if running as administrator."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    @staticmethod
    def check_microphone():
        """Check microphone access."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            mics = [d for d in devices if d['max_input_channels'] > 0]
            if mics:
                return True, f"✅ {len(mics)} microphone(s) available"
            else:
                return False, "❌ No microphones found"
        except Exception as e:
            return False, f"❌ Error: {e}"

    @staticmethod
    def check_speaker():
        """Check speaker access."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            speakers = [d for d in devices if d['max_output_channels'] > 0]
            if speakers:
                return True, f"✅ {len(speakers)} speaker(s) available"
            else:
                return False, "❌ No speakers found"
        except Exception as e:
            return False, f"❌ Error: {e}"

    @staticmethod
    def check_camera():
        """Check camera access."""
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.release()
                return True, "✅ Camera accessible"
            else:
                return False, "❌ Camera not accessible"
        except ImportError:
            return False, "⚠️  OpenCV not installed (optional)"
        except Exception as e:
            return False, f"❌ Error: {e}"

    @staticmethod
    def check_file_access():
        """Check file system access."""
        try:
            test_file = Path.home() / ".mark_liv_test"
            test_file.write_text("test")
            test_file.unlink()
            return True, "✅ File system accessible"
        except Exception as e:
            return False, f"❌ Error: {e}"

    @staticmethod
    def check_network():
        """Check network access."""
        try:
            import socket
            socket.setdefaulttimeout(2)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True, "✅ Network accessible"
        except:
            return False, "❌ Network not accessible"

    @staticmethod
    def check_gemini_api():
        """Check Gemini API key configuration."""
        try:
            from core.gemini import api_key
            key = api_key()
            if key:
                return True, "✅ Gemini API key configured"
            else:
                return False, "❌ Gemini API key missing"
        except Exception as e:
            return False, f"❌ Error: {e}"

    @staticmethod
    def check_all():
        """Check all permissions and return status."""
        checks = {
            "Administrator": PermissionChecker.is_admin(),
            "Microphone": PermissionChecker.check_microphone()[0],
            "Speaker": PermissionChecker.check_speaker()[0],
            "Camera": PermissionChecker.check_camera()[0],
            "File Access": PermissionChecker.check_file_access()[0],
            "Network": PermissionChecker.check_network()[0],
            "Gemini API": PermissionChecker.check_gemini_api()[0],
        }

        return checks

    @staticmethod
    def print_status():
        """Print detailed permission status."""
        print("\n" + "=" * 60)
        print("MARK LIV Permission Status")
        print("=" * 60)

        # Admin
        admin = PermissionChecker.is_admin()
        print(f"\nAdministrator: {'✅ Yes' if admin else '❌ No'}")
        if not admin:
            print("   ⚠️  Some features may require administrator privileges")

        # Microphone
        mic_ok, mic_msg = PermissionChecker.check_microphone()
        print(f"\nMicrophone: {mic_msg}")

        # Speaker
        spk_ok, spk_msg = PermissionChecker.check_speaker()
        print(f"Speaker: {spk_msg}")

        # Camera
        cam_ok, cam_msg = PermissionChecker.check_camera()
        print(f"Camera: {cam_msg}")

        # File Access
        file_ok, file_msg = PermissionChecker.check_file_access()
        print(f"File Access: {file_msg}")

        # Network
        net_ok, net_msg = PermissionChecker.check_network()
        print(f"Network: {net_msg}")

        # Gemini API
        api_ok, api_msg = PermissionChecker.check_gemini_api()
        print(f"Gemini API: {api_msg}")

        print("\n" + "=" * 60)

        # Summary
        all_required = admin and mic_ok and spk_ok and file_ok and net_ok and api_ok
        if all_required:
            print("✅ All required permissions are granted!")
        else:
            print("⚠️  Some permissions are missing.")
            print("   Run 'python setup_permissions.py' to grant permissions.")

        print("=" * 60 + "\n")

        return all_required


if __name__ == "__main__":
    PermissionChecker.print_status()
