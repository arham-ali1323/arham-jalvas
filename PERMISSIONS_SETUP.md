# MARK LIV Permission Setup Guide

This guide explains how to grant MARK LIV the necessary permissions to run properly on Windows.

## Quick Start

### Option 1: Interactive Setup (Recommended)

Run the permission setup script interactively:

```bash
python setup_permissions.py
```

This will:
1. Check if you're running as administrator
2. Show current permission status
3. Let you choose which permissions to grant

### Option 2: Automatic Setup

Grant all permissions automatically:

```bash
python setup_permissions.py --auto
```

⚠️ **Warning:** This grants all permissions without confirmation. Only use if you trust the application.

## Permissions Explained

MARK LIV requires the following permissions:

### 1. Administrator Privileges
- **Purpose:** Required for system-level operations (file access, system monitoring)
- **How to grant:** Right-click → "Run as administrator"

### 2. Microphone Access
- **Purpose:** Voice input for JARVIS
- **How to grant:**
  - Settings → Privacy → Microphone → Allow apps to access your microphone → ON
  - Or run the setup script

### 3. Speaker Access
- **Purpose:** Voice output from JARVIS
- **Usually granted:** By default on Windows

### 4. Camera Access (Optional)
- **Purpose:** Vision capabilities
- **How to grant:**
  - Settings → Privacy → Camera → Allow apps to access your camera → ON
  - Or run the setup script

### 5. File System Access
- **Purpose:** Reading/writing files, memory system
- **How to grant:**
  - Add to Windows Defender exclusions
  - Or run the setup script

### 6. Network Access
- **Purpose:** Gemini API, DuckDuckGo search, web services
- **How to grant:**
  - Windows Firewall exception
  - Or run the setup script

## Manual Setup (Without Script)

If you prefer manual setup:

### Step 1: Run as Administrator
Right-click MARK LIV or Python and select "Run as administrator"

### Step 2: Privacy Settings
1. Open Settings → Privacy
2. Enable Microphone access
3. Enable Camera access (if using vision features)

### Step 3: Windows Defender
1. Open Windows Security → Virus & threat protection
2. Go to Ransomware protection → Controlled folder access
3. Click "Block history" or add MARK LIV to allowed apps
4. Or add to exclusions: Manage settings → Exclusions → Add an exclusion

### Step 4: Firewall
1. Open Windows Defender Firewall
2. Click "Allow an app through firewall"
3. Click "Change settings" (requires admin)
4. Find MARK LIV or Python
5. Check both Private and Public networks

## Check Permissions

Run the permission checker:

```bash
python core/permissions.py
```

Or ask JARVIS directly:
```
You: "JARVIS, check my permissions"
JARVIS: [Will run dev_helper with check_permissions action]
```

## Troubleshooting

### "Script requires administrator privileges"
- Right-click Command Prompt → "Run as administrator"
- Then run: `python setup_permissions.py`

### "Could not grant microphone permission"
- Manually enable in: Settings → Privacy → Microphone
- Make sure "Allow apps to access your microphone" is ON

### "Could not add firewall exception"
- Manually add in: Windows Defender Firewall → Allow an app
- Browse to the Python executable or MARK LIV executable

### "Microphone not found"
- Check if you have a microphone connected
- Go to Settings → System → Sound → Input
- Select your microphone and test it

### "Network not accessible"
- Check your internet connection
- Ensure Windows Firewall isn't blocking
- Run: `ping 8.8.8.8` to test connectivity

## Security Best Practices

1. **Review the code:** MARK LIV is open-source - review what it does
2. **Start minimal:** Only grant permissions you need
3. **Use a dedicated account:** Create a separate Windows user for MARK LIV
4. **Monitor activity:** Watch what files MARK LIV accesses
5. **Keep updated:** Keep MARK LIV and dependencies updated

## Revoke Permissions

To revoke permissions later:

### Remove Firewall Exception
```bash
netsh advfirewall firewall delete rule name="MARK LIV"
```

### Remove from Windows Defender Exclusions
```powershell
Remove-MpPreference -ExclusionPath "path/to/mark/liv"
```

### Reset Privacy Settings
Settings → Privacy → Reset (for each category)

## Support

If you encounter issues:
1. Run `python core/permissions.py` to check status
2. Run `python setup_permissions.py` to re-grant permissions
3. Check the logs in the MARK LIV directory
4. Review this guide's troubleshooting section

## Files Created

- `setup_permissions.py` - Permission setup script
- `core/permissions.py` - Permission checker module
- `PERMISSIONS_SETUP.md` - This guide

These files are safe to review and modify as needed.
