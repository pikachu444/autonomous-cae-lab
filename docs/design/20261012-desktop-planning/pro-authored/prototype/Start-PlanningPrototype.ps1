param(
    [Parameter(Mandatory = $true)]
    [string]$PythonPath,
    [string]$StatePath = "",
    [switch]$MaterialOnly
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Provide the actual python.exe path in your existing PySide6 + Matplotlib environment. No installation is performed."
}
$probe = @'
import sys
import PySide6
from PySide6 import QtCore, QtGui, QtWidgets, QtUiTools
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
print('Existing Python:', sys.executable)
print('PySide6:', PySide6.__version__, 'Qt:', QtCore.qVersion(), 'Matplotlib:', matplotlib.__version__)
if PySide6.__version__ != '6.9.1':
    print('NOTICE: planning target is PySide6 6.9.1; actual installed version differs.')
'@
& $PythonPath -c $probe
if ($LASTEXITCODE -ne 0) {
    throw "Existing environment lacks one or more required modules. No packages were installed. Use the correct PythonPath."
}
$entryPath = Join-Path $PSScriptRoot "gallery.py"
$arguments = @($entryPath)
if ($StatePath) { $arguments += @("--state", $StatePath) }
if ($MaterialOnly) { $arguments += "--material-only" }
Write-Host "Launching SIMULATED UI planning prototype. No fit, solver, provider or production service."
& $PythonPath @arguments
exit $LASTEXITCODE
