param(
  [int]$BackendProcessId = 0
)

$ErrorActionPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot "backend\logs"
$logPath = Join-Path $logDirectory "local-shutdown.log"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

function Write-ShutdownLog {
  param([string]$Message)
  Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) $Message"
}

Start-Sleep -Seconds 2
Write-ShutdownLog "Shutdown requested by backend PID $BackendProcessId."

# Win32's process snapshot API works without the WMI/CIM permissions that are
# unavailable in some local Windows sessions. It lets us stop the whole Next.js
# process chain instead of only its child listener, which Next.js can restart.
if (-not ("JusticeKpProcessTree" -as [type])) {
  Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public sealed class JusticeKpProcessInfo
{
    public int ProcessId { get; set; }
    public int ParentProcessId { get; set; }
    public string Name { get; set; }
}

public static class JusticeKpProcessTree
{
    private const uint TH32CS_SNAPPROCESS = 0x00000002;
    private static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct PROCESSENTRY32
    {
        public uint dwSize;
        public uint cntUsage;
        public uint th32ProcessID;
        public IntPtr th32DefaultHeapID;
        public uint th32ModuleID;
        public uint cntThreads;
        public uint th32ParentProcessID;
        public int pcPriClassBase;
        public uint dwFlags;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint processId);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool Process32First(IntPtr snapshot, ref PROCESSENTRY32 entry);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool Process32Next(IntPtr snapshot, ref PROCESSENTRY32 entry);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    public static JusticeKpProcessInfo[] GetProcesses()
    {
        var processes = new List<JusticeKpProcessInfo>();
        IntPtr snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == INVALID_HANDLE_VALUE)
        {
            return processes.ToArray();
        }

        try
        {
            var entry = new PROCESSENTRY32();
            entry.dwSize = (uint)Marshal.SizeOf(typeof(PROCESSENTRY32));
            if (!Process32First(snapshot, ref entry))
            {
                return processes.ToArray();
            }

            do
            {
                processes.Add(new JusticeKpProcessInfo
                {
                    ProcessId = (int)entry.th32ProcessID,
                    ParentProcessId = (int)entry.th32ParentProcessID,
                    Name = entry.szExeFile ?? string.Empty
                });
            }
            while (Process32Next(snapshot, ref entry));
        }
        finally
        {
            CloseHandle(snapshot);
        }

        return processes.ToArray();
    }
}
"@
}

function Get-ListeningProcessIds {
  param([int]$Port)

  $processIds = [System.Collections.Generic.HashSet[int]]::new()
  foreach ($line in (netstat.exe -ano -p tcp)) {
    if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
      [void]$processIds.Add([int]$Matches[1])
    }
  }
  return @($processIds)
}

function Get-ServerProcessChain {
  param(
    [int]$StartProcessId,
    [string[]]$AllowedProcessNames
  )

  $snapshot = [JusticeKpProcessTree]::GetProcesses()
  $processById = @{}
  foreach ($process in $snapshot) {
    $processById[[int]$process.ProcessId] = $process
  }

  $processIds = [System.Collections.Generic.List[int]]::new()
  $currentId = $StartProcessId
  while ($currentId -gt 0 -and -not $processIds.Contains($currentId)) {
    # Always include the known listener/backend PID, even if its metadata cannot
    # be read. This prevents a permissions failure from turning shutdown into a no-op.
    $processIds.Add($currentId)
    $current = $processById[$currentId]
    if (-not $current) { break }

    $parent = $processById[[int]$current.ParentProcessId]
    if (-not $parent -or $AllowedProcessNames -notcontains $parent.Name.ToLowerInvariant()) {
      break
    }
    $currentId = [int]$parent.ProcessId
  }
  return @($processIds)
}

function Stop-ProcessChain {
  param(
    [int[]]$ProcessIds,
    [string]$Label
  )

  # The chain is leaf-to-root. Stopping every member prevents a development
  # launcher from immediately replacing a terminated listener process.
  foreach ($processId in $ProcessIds) {
    Write-ShutdownLog "Stopping $Label process $processId."
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
}

# Next.js development mode uses several node/cmd processes. Repeat discovery
# briefly in case its launcher creates one last replacement during shutdown.
for ($attempt = 1; $attempt -le 6; $attempt++) {
  $frontendListeners = @(Get-ListeningProcessIds -Port 3000)
  if ($frontendListeners.Count -eq 0) { break }

  foreach ($listenerProcessId in $frontendListeners) {
    $chain = @(Get-ServerProcessChain -StartProcessId $listenerProcessId -AllowedProcessNames @("node.exe", "cmd.exe"))
    Stop-ProcessChain -ProcessIds $chain -Label "frontend"
  }
  Start-Sleep -Milliseconds 500
}

$remainingFrontend = @(Get-ListeningProcessIds -Port 3000)
Write-ShutdownLog "Frontend listeners remaining: $($remainingFrontend -join ',')."

$backendIds = [System.Collections.Generic.HashSet[int]]::new()
if ($BackendProcessId -gt 0) {
  [void]$backendIds.Add($BackendProcessId)
}
foreach ($listenerProcessId in (Get-ListeningProcessIds -Port 8000)) {
  [void]$backendIds.Add([int]$listenerProcessId)
}

foreach ($backendId in $backendIds) {
  $chain = @(Get-ServerProcessChain -StartProcessId $backendId -AllowedProcessNames @("python.exe", "pythonw.exe"))
  Stop-ProcessChain -ProcessIds $chain -Label "backend"
}

Start-Sleep -Milliseconds 750
foreach ($remainingBackendId in (Get-ListeningProcessIds -Port 8000)) {
  Write-ShutdownLog "Stopping remaining backend listener $remainingBackendId."
  Stop-Process -Id $remainingBackendId -Force -ErrorAction SilentlyContinue
}

Write-ShutdownLog "Shutdown helper finished."
