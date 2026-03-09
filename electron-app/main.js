const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let flaskProcess;

function createWindow() {
    // Create the browser window.
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        icon: path.join(__dirname, 'icon.ico'), // will add icon later
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
        },
        show: false, // wait for page to load before showing
    });

    // Load the Flask app (assuming it runs on localhost:5000)
    mainWindow.loadURL('http://localhost:5000/auth/login');

    // Show window when ready
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // Emitted when the window is closed.
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// Start Flask server as a child process
function startFlask() {
    // Adjust the command based on your OS and environment
    // On Windows, you might need to use 'python' or 'python.exe'
    // If you're inside a virtual environment, you can call the full path to python
    const pythonExecutable = path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe'); // adjust path!
    const scriptPath = path.join(__dirname, '..', 'run.py'); // your Flask entry point

    flaskProcess = spawn(pythonExecutable, [scriptPath], {
        cwd: path.join(__dirname, '..'), // root of your Flask project
        env: { ...process.env, FLASK_ENV: 'production' } // optionally set environment
    });

    flaskProcess.stdout.on('data', (data) => {
        console.log(`Flask stdout: ${data}`);
    });

    flaskProcess.stderr.on('data', (data) => {
        console.error(`Flask stderr: ${data}`);
    });

    flaskProcess.on('close', (code) => {
        console.log(`Flask process exited with code ${code}`);
    });
}

// This method will be called when Electron has finished initialization
app.whenReady().then(() => {
    startFlask();
    // Give Flask a moment to start before opening the window
    setTimeout(createWindow, 3000); // adjust delay if needed
});

// Quit when all windows are closed.
app.on('window-all-closed', () => {
    // On macOS it is common for applications to stay open until the user quits explicitly
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    // On macOS it's common to re-create a window when the dock icon is clicked
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// Clean up the Flask process when Electron exits
app.on('will-quit', () => {
    if (flaskProcess) {
        flaskProcess.kill();
    }
});