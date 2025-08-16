@echo off

REM This script starts the MongoDB server.

REM Set the path to your mongod.exe
set MONGO_EXECUTABLE="C:\Devops\mongoDB\bin\mongod.exe"

REM Set the path for the database files, to a neutral location
set DB_PATH="C:\athba_data\db"

REM Check if the mongod.exe exists
if not exist %MONGO_EXECUTABLE% (
    echo ERROR: MongoDB executable not found at %MONGO_EXECUTABLE%
    echo Please update the MONGO_EXECUTABLE path in this script.
    pause
    exit /b
)

REM Create the data directory if it doesn't exist
if not exist %DB_PATH% (
    echo Creating database directory at %DB_PATH%
    mkdir %DB_PATH%
)

echo Starting MongoDB server...
echo This will run mongod in the current window. Close the window to stop the server.

%MONGO_EXECUTABLE% --dbpath %DB_PATH%