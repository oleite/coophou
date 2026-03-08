# coophou (Houdini Package)

Work-in-progress, allowing multiple users to collaborate on the same Houdini scene in real time.

## Installation

### Windows

Run the following in a Command Prompt:

```bat
:: Change the path to your Houdini user directory if needed
set "HOUDINI_PATH=%USERPROFILE%\Documents\houdini21.0"
set "PACKAGES_PATH=%HOUDINI_PATH%\packages"

:: Clone the repository
mkdir "%PACKAGES_PATH%"
cd "%PACKAGES_PATH%"
git clone https://github.com/oleite/coophou.git

:: Copy the package definition into the packages directory
copy "coophou\coophou.json" "%PACKAGES_PATH%\coophou.json"

:: Done! Restart Houdini to load the package.
```

### Linux

Run the following in a terminal:

```bash
# Change the path to your Houdini user directory if needed
HOUDINI_PATH="$HOME/houdini21.0"
PACKAGES_PATH="$HOUDINI_PATH/packages"

# Clone the repository
mkdir -p "$PACKAGES_PATH"
cd "$PACKAGES_PATH"
git clone https://github.com/oleite/coophou.git

# Copy the package definition into the packages directory
cp coophou/coophou.json "$PACKAGES_PATH/coophou.json"

# Done! Restart Houdini to load the package.
```

## Development

For testing, you can use this helper to launch side-by-side Houdini sessions, the first one as server, the rest as clients:

```bat
python scripts/launchHoudiniSessions.py --sessions 2
```