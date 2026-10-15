# SPDX-License-Identifier: BSD-3-Clause
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$WorkRoot,
    [Parameter(Mandatory=$true)][string]$Python
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'This build glue is only for the dedicated GitHub-hosted CI VM; use the existing local build script locally.'
}
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$root = (Resolve-Path -LiteralPath $WorkRoot).Path
$source = Join-Path $root 'source/ParaView-v6.2.0'
$qt = Join-Path $root 'qt'
$sdkBuild = Join-Path $root 'sdk-build'
$runtime = Join-Path $root 'runtime'
$pluginBuild = Join-Path $root 'plugin-build'
$evidencePath = Join-Path $root 'build-evidence.json'
foreach ($path in @($sdkBuild,$runtime,$pluginBuild,$evidencePath)) {
    if (Test-Path -LiteralPath $path) { throw "Use a new CI work directory; preserve the prior build/evidence: $path" }
}
$evidence = [ordered]@{source_commit=(& git -C $repo rev-parse HEAD); sdk_build='NOT_RUN';
    plugin_build='NOT_RUN'; native_backend='NOT_RUN'; desktop_exit_acceptance='NOT_RUN';
    artifact_upload='NONE'; release_publication='NONE'; runner_image=$env:ImageVersion}

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
    Write-Output "SDK_DISK before program=$Program volume=$($drive.Name) available_bytes=$($drive.AvailableFreeSpace)"
    & $Program @Arguments
    $exitCode = $LASTEXITCODE
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
    Write-Output "SDK_DISK after program=$Program volume=$($drive.Name) available_bytes=$($drive.AvailableFreeSpace) exit=$exitCode"
    if ($exitCode -ne 0) { throw "Native step failed: $Program (exit $exitCode)" }
}

function Import-VisualStudioEnvironment {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Existing Visual Studio C++ Build Tools are required.' }
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0 -or -not $vs) { throw 'No installed x64 MSVC toolchain was found.' }
    $vsDevCmd = Join-Path $vs 'Common7/Tools/VsDevCmd.bat'
    # Capture, do not print, the environment. Import only compiler/SDK paths into
    # this dedicated process; no user/system environment or VS installation edits.
    $lines = & $env:ComSpec /d /c "call `"$vsDevCmd`" -arch=amd64 -host_arch=amd64 -no_logo >nul && set"
    if ($LASTEXITCODE -ne 0) { throw 'Existing x64 Native Tools environment failed.' }
    $allowed = @('PATH','INCLUDE','LIB','LIBPATH','VCToolsInstallDir','VCINSTALLDIR','VSINSTALLDIR',
        'WindowsSdkDir','WindowsSDKVersion','VSCMD_ARG_HOST_ARCH','VSCMD_ARG_TGT_ARCH','VisualStudioVersion','VCToolsVersion')
    foreach ($line in $lines) {
        if ($line -match '^([^=]+)=(.*)$' -and $Matches[1] -in $allowed) {
            [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2],'Process')
        }
    }
    $evidence['visual_studio'] = $vs
    $evidence['compiler_path'] = (Get-Command cl.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $evidence['compiler_file_version'] = (Get-Item -LiteralPath $evidence.compiler_path).VersionInfo.FileVersion
    $toolset = [version]$env:VCToolsVersion
    if ($toolset -lt [version]'14.39') { throw 'The selected linker/toolset predates the pinned Qt MSVC2022 build.' }
    $crt = @{}
    foreach ($name in @('vcruntime140.dll','msvcp140.dll')) {
        $info = (Get-Item -LiteralPath (Join-Path $env:WINDIR "System32/$name")).VersionInfo
        $version = [version]::new($info.FileMajorPart,$info.FileMinorPart,$info.FileBuildPart,$info.FilePrivatePart)
        if ($version -lt $toolset) { throw "System CRT is older than the selected MSVC toolset: $name" }
        $crt[$name] = $version.ToString()
    }
    $evidence['system_crt_versions'] = $crt
}

function Invoke-OwnedCheck([string]$Name, [string[]]$Command, [int]$Timeout=180) {
    $jobDir = Join-Path $root "checks/$Name"
    Invoke-Checked $Python (@((Join-Path $repo 'scripts/native_check.py'),'--timeout',[string]$Timeout,
        '--output-dir',$jobDir,'--') + $Command)
    $receipt = Get-Content -LiteralPath (Join-Path $jobDir 'native-check.json') -Raw | ConvertFrom-Json
    if ($receipt.cleanup -ne 'job_empty' -or $receipt.cleanup_error -or $receipt.exit_code -ne 0) {
        throw "Owned native check did not finish cleanly: $Name"
    }
}

try {
    foreach ($path in @('inputs.json','source/ParaView-v6.2.0/CMakeLists.txt','qt/lib/cmake/Qt6/Qt6Config.cmake')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $path))) { throw "Missing verified SDK input: $path" }
    }
    $inputs = Get-Content -LiteralPath (Join-Path $root 'inputs.json') -Raw | ConvertFrom-Json
    foreach ($inputFile in $inputs.inputs) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $root "downloads/$($inputFile.file)") -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $inputFile.sha256) { throw "Verified input changed: $($inputFile.file)" }
    }
    $pythonInfo = (& $Python -c 'import json,struct,sys; print(json.dumps({"version":sys.version.split()[0],"bits":struct.calcsize("P")*8,"prefix":sys.base_prefix}))') | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $pythonInfo.version -ne '3.12.10' -or $pythonInfo.bits -ne 64) {
        throw 'This workflow requires its pinned CPython 3.12.10 x64 environment.'
    }
    foreach ($path in @('include/Python.h','libs/python312.lib','python312.dll','LICENSE.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $pythonInfo.prefix $path))) { throw "Python development/license file missing: $path" }
    }
    $evidence['python'] = $pythonInfo
    $evidence['python_dll_sha256'] = (Get-FileHash -LiteralPath (Join-Path $pythonInfo.prefix 'python312.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    # One exact official PyPI wheel, already SHA256-checked; no resolver/network,
    # pip cache, dependency downloads or installation into an existing user runtime.
    Invoke-Checked $Python @('-m','pip','install','--no-index','--no-deps','--no-cache-dir',
        (Join-Path $root 'downloads/numpy-2.3.5-cp312-cp312-win_amd64.whl'))
    Import-VisualStudioEnvironment
    $cmake = (Get-Command cmake.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $env:PATH = "$qt/bin;$($pythonInfo.prefix);$env:PATH"
    $env:MSBUILDDISABLENODEREUSE = '1'
    $env:UseMultiToolTask = 'true'
    $env:EnforceProcessCountAcrossBuilds = 'true'
    $env:MultiProcMaxCount = '2'
    $env:CL_MPCount = '2'
    $env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
    $configure = @('-S',$source,'-B',$sdkBuild,'-G','Visual Studio 17 2022','-A','x64','-T','host=x64',
        '-DCMAKE_CONFIGURATION_TYPES=Release','-DCMAKE_BUILD_TYPE=Release',
        '-DPARAVIEW_USE_QT=ON','-DPARAVIEW_QT_MAJOR_VERSION=6','-DPARAVIEW_USE_PYTHON=ON',
        '-DPARAVIEW_USE_MPI=OFF','-DPARAVIEW_ENABLE_WEB=OFF','-DPARAVIEW_BUILD_SHARED_LIBS=ON',
        '-DPARAVIEW_BUILD_TESTING=OFF','-DPARAVIEW_INSTALL_DEVELOPMENT_FILES=ON',
        '-DPARAVIEW_PLUGINS_DEFAULT=OFF',
        '-DPARAVIEW_ENABLE_EMBEDDED_DOCUMENTATION=OFF','-DPARAVIEW_PLUGIN_DISABLE_XML_DOCUMENTATION=ON',
        # VTK writes Python paths into quoted CMake source; use CMake separators.
        "-DCMAKE_PREFIX_PATH=$qt","-DPython3_ROOT_DIR=$($pythonInfo.prefix.Replace('\','/'))","-DPython3_EXECUTABLE=$($Python.Replace('\','/'))",
        "-DCMAKE_INSTALL_PREFIX=$runtime")
    Invoke-Checked $cmake $configure
    # Obtain the exact plugin dependency closure first. No default solver or
    # unrelated campaign is started by this target.
    Invoke-Checked $cmake @('--build',$sdkBuild,'--config','Release','--target','pqComponents','--parallel','2','--','/nodeReuse:false')
    $evidence['sdk_build'] = 'PLUGIN_DEPENDENCIES_BUILT'
    & (Join-Path $repo 'native/post_exit/Build-PostExit.ps1') -ParaViewDir (Join-Path $sdkBuild 'lib/cmake/paraview-6.2') `
        -Qt6Dir (Join-Path $qt 'lib/cmake/Qt6') -BuildDir $pluginBuild -Python $Python -Generator 'Visual Studio 17 2022'
    $coreJob = Join-Path $pluginBuild 'core-test-job'
    $coreReceipt = Get-Content -LiteralPath (Join-Path $coreJob 'native-check.json') -Raw | ConvertFrom-Json
    if ($coreReceipt.exit_code -ne 0 -or $coreReceipt.cleanup -ne 'job_empty' -or $coreReceipt.cleanup_error) {
        throw 'Existing core/C ABI checks did not finish in an empty owned Job.'
    }
    $coreLog = Get-Content -LiteralPath (Join-Path $coreJob 'stdout.log') -Raw
    foreach ($name in @('cae_exit_transaction','cae_exit_c_python_abi')) {
        if ($coreLog -notmatch [regex]::Escape($name)) { throw "Expected native check was not run: $name" }
    }
    Write-Output $coreLog
    if (-not (Test-Path -LiteralPath (Join-Path $pluginBuild 'bin/Release/cae_exit_qt.exe'))) {
        throw 'The existing Qt event harness was not compiled.'
    }
    $evidence['plugin_build'] = 'BUILT_CORE_AND_C_ABI_CHECKS_PASSED_QT_HARNESS_COMPILED'
    # The same source/toolchain runtime and Python wrappers are necessary for
    # native reader checks. Do not bind this SDK to the user's stock bundle.
    # The official install exports every configured SDK target. Complete those
    # outputs before installing; otherwise an unbuilt utility/plugin import can
    # invalidate the install. Optional default plugins are disabled above.
    Invoke-Checked $cmake @('--build',$sdkBuild,'--config','Release','--parallel','2','--','/nodeReuse:false')
    $evidence['sdk_build'] = 'CONFIGURED_RUNTIME_SDK_AND_PYTHON_TARGETS_BUILT'
    # Keep runtime/development installation diagnostics literal. Missing build
    # outputs must fail rather than silently copying a different stock runtime.
    Invoke-Checked $cmake @('--install',$sdkBuild,'--config','Release','--component','runtime')
    Invoke-Checked $cmake @('--install',$sdkBuild,'--config','Release','--component','development')
    Invoke-Checked $cmake @('--install',$sdkBuild,'--config','Release','--component','python')
    $evidence['sdk_build'] = 'RUNTIME_AND_DEVELOPMENT_INSTALL_COMPLETED'
    $env:PATH = "$(Join-Path $runtime 'bin');$env:PATH"
    $deployQt = Join-Path $qt 'bin/windeployqt.exe'
    Invoke-Checked $deployQt @('--release','--no-compiler-runtime','--no-translations',
        (Join-Path $runtime 'bin/paraview.exe'))
    Copy-Item -LiteralPath (Join-Path $pythonInfo.prefix 'python312.dll') -Destination (Join-Path $runtime 'bin/python312.dll')
    $env:PYTHONHOME = $pythonInfo.prefix
    $env:PYTHONPATH = "$repo;$(Join-Path $runtime 'lib/site-packages')"
    $env:QT_PLUGIN_PATH = Join-Path $runtime 'bin'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $plugin = @(Get-ChildItem -LiteralPath (Join-Path $pluginBuild 'bin') -Recurse -Filter 'CaePostExit.dll')
    if ($plugin.Count -ne 1) { throw 'Expected one exact built plugin DLL.' }
    $sdkFiles = @{}
    foreach ($file in @((Join-Path $sdkBuild 'CMakeCache.txt'),(Join-Path $pluginBuild 'CMakeCache.txt'),
        (Join-Path $qt 'lib/cmake/Qt6/Qt6Config.cmake'),(Join-Path $root 'inputs.json'))) {
        $sdkFiles[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $sdkEvidence = Join-Path $root 'sdk-evidence.json'
    @{schema='cae.post-exit-sdk/1'; runtime_relationship='same-sdk-build'; files=$sdkFiles} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $sdkEvidence -Encoding utf8
    $evidence['sdk_files'] = $sdkFiles
    Invoke-Checked $Python @((Join-Path $repo 'scripts/post_exit_artifact.py'),'--plugin',$plugin[0].FullName,
        '--runtime',$runtime,'--build-info',(Join-Path $pluginBuild 'cae-post-exit-build-info.json'),'--sdk-evidence',$sdkEvidence)
    $pvpython = Join-Path $runtime 'bin/pvpython.exe'
    # Preserve direct PE imports before a loader failure can prevent Python diagnostics.
    $dumpbin = (Get-Command dumpbin.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $dependencyLog = Join-Path $root 'checks/load-dependencies.log'
    New-Item -ItemType Directory -Path (Split-Path -Parent $dependencyLog) -Force | Out-Null
    foreach ($binary in @($pvpython,(Join-Path $runtime 'bin/python312.dll'))) {
        Write-Output "--- Direct imports: $binary" | Add-Content -LiteralPath $dependencyLog -Encoding utf8
        Invoke-Checked $dumpbin @('/DEPENDENTS',$binary) | Add-Content -LiteralPath $dependencyLog -Encoding utf8
    }
    Get-ChildItem -LiteralPath (Join-Path $runtime 'bin') -File -Filter '*.dll' |
        Sort-Object Name | ForEach-Object { "INSTALLED_RUNTIME_DLL $($_.Name)" } |
        Add-Content -LiteralPath $dependencyLog -Encoding utf8
    $closureLog = Join-Path $root 'checks/load-dependency-closure.log'
    try {
        Invoke-Checked $cmake @("-DPOST_PVPYTHON=$($pvpython.Replace('\','/'))",
            "-DPOST_DUMPBIN=$($dumpbin.Replace('\','/'))",'-P',
            (Join-Path $repo 'scripts/post_native_windows_dependencies.cmake')) *> $closureLog
    } catch {
        Add-Content -LiteralPath $closureLog -Value "DIAGNOSTIC_ERROR $_" -Encoding utf8
    }
    Invoke-OwnedCheck 'load' @($pvpython,(Join-Path $repo 'scripts/post_native_windows_smoke.py'),'--plugin',$plugin[0].FullName)
    $evidence['native_backend'] = 'PLUGIN_LOAD_PASSED_COMPARISON_NOT_COMPLETED'
    $comparison = Join-Path $root 'checks/comparison'
    Invoke-OwnedCheck 'create' @($pvpython,(Join-Path $repo 'tests/check_post_comparison_native.py'),'--create',$comparison) 300
    $evidence['native_backend'] = 'PLUGIN_LOAD_AND_COMPARISON_SAVE_PASSED_COLD_NOT_COMPLETED'
    Invoke-OwnedCheck 'cold' @($pvpython,(Join-Path $repo 'tests/check_post_comparison_native.py'),'--reopen',(Join-Path $comparison 'receipt.json')) 300
    $evidence['native_backend'] = 'PLUGIN_LOAD_EXISTING_COMPARISON_SAVE_AND_COLD_REOPEN_PASSED'
    $evidence['plugin_sha256'] = (Get-FileHash -LiteralPath $plugin[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output 'SDK/plugin/native backend checks finished. Actual Windows ParaView GUI exit acceptance is NOT_RUN.'
} finally {
    $evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $evidencePath -Encoding utf8
    $evidence | ConvertTo-Json -Depth 6 | Write-Output
}
