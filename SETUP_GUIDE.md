# Run DevOps Runbook on Windows

Follow these steps in order.

## 1. Check that Git and Python are installed

Install Git and Python 3.9 or newer if needed. During Python installation, enable the Python Launcher.

## 2. Open PowerShell

Open the Start menu, search for **PowerShell**, and open it.

## 3. Choose where to save the project

This example saves it in Downloads. To use another folder, replace this path with that folder's path.

```powershell
Set-Location "$HOME\Downloads"
```

## 4. Clone the repository

```powershell
git clone https://github.com/KishanNigam/DevOps_Runbook.git
```

## 5. Enter the project folder

```powershell
Set-Location .\DevOps_Runbook
```

## 6. Create a virtual environment

```powershell
py -m venv .venv
```

## 7. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

## 8. Install the project dependencies

```powershell
python -m pip install -r requirements.txt
```

## 9. Start the application

```powershell
python app.py
```

## 10. Open the website

Open this address in your browser:

<http://127.0.0.1:5000/>

## 11. Stop the application

Return to the PowerShell window running the application. Press **Ctrl+C**.

## If something goes wrong

- **Python is not found:** Install Python 3.9 or newer with the Python Launcher enabled. Close and reopen PowerShell, then try `py --version`.
- **Dependency installation fails:** Check your internet connection and run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- **Port 5000 is already in use:** Close the other application using port 5000, then run `python app.py` again.

## Verification

The clone, virtual-environment, dependency-install, and startup steps were tested on Windows using a fresh clone. The homepage returned HTTP 200 at the address above.
