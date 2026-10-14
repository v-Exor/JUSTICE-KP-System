# Private Tailscale demo access

This runs the existing local demo on this Windows PC. Tailscale provides the
encrypted connection; transcription still uses this PC's CPU/GPU. The PC must
stay awake, online, and running both application servers.

## Proposed routing

| Private HTTPS endpoint | Local server |
| --- | --- |
| `https://<this-pc>.<tailnet>.ts.net` | `http://127.0.0.1:3000` frontend |
| `https://<this-pc>.<tailnet>.ts.net:8443` | `http://127.0.0.1:8000` backend |

Both are Tailscale Serve endpoints, accessible according to the tailnet's access
policy. Devices need Tailscale access to this PC and both ports. This does not use
public Tailscale Funnel, router forwarding, an exit node, or subnet routing.
The app's existing login and role checks still apply.

## Enable sharing once authorized

In Administrator PowerShell, inspect existing routes before changing anything:

```powershell
& "$env:ProgramFiles\Tailscale\tailscale.exe" serve status
```

If ports 443 and 8443 are unused, enable these two routes:

```powershell
& "$env:ProgramFiles\Tailscale\tailscale.exe" serve --bg --https=443 http://127.0.0.1:3000
& "$env:ProgramFiles\Tailscale\tailscale.exe" serve --bg --https=8443 http://127.0.0.1:8000
```

If prompted, follow Tailscale's link to enable HTTPS for the tailnet, then rerun
the command. These background routes persist across restarts.

## Start the app

Double-click **Start JUSTICE-KP.cmd** in the project folder. It checks Tailscale,
the two saved HTTPS routes, installed runtimes, and available ports, then opens
separate **JUSTICE-KP Backend** and **JUSTICE-KP Frontend** PowerShell windows.
Wait until both servers finish starting, then open the HTTPS URL printed in
either window. Leave both windows open while the website is in use.

If something prevents startup, the launcher displays an error. If it reports
Tailscale access denied, right-click the launcher and choose **Run as administrator**.
If the app is already running, use the existing windows; to restart, press Ctrl+C
in both old windows first. The launcher does not terminate existing processes.

You can create a Windows shortcut to this file on your Desktop. Keep the actual
CMD file in the project folder so it can find the scripts. The launcher uses a
PowerShell execution-policy override for its own processes only; it does not
change the system execution policy or configure Tailscale sharing.

For local development, use **Start JUSTICE-KP Local.cmd** and open
`http://127.0.0.1:3000`. Stop both servers before switching launchers, since they
use the same ports and project data. Saved Serve routes still point at these
ports in local mode; disconnect Tailscale on this PC for access limited to this PC.

For manual Tailscale startup instead:

Stop any existing local frontend/backend terminals first. From the project root,
run each command in its own PowerShell terminal and leave both running:

```powershell
.\scripts\run_tailscale_app.ps1 -Service Backend
```

```powershell
.\scripts\run_tailscale_app.ps1 -Service Frontend
```

The launcher discovers this PC's Tailscale hostname, sets the frontend's HTTPS
API address, permits the exact frontend origin in the backend, and disables
the local shutdown endpoint while serving remotely. Both servers still bind to
loopback. It does not change saved environment files or enable sharing itself.

Open the printed **HTTPS** app URL on a device connected to the same tailnet.
Use that URL consistently in this mode, including on the host PC. Grant browser
microphone permission when recording. The old local demo scripts still work
when you stop these servers and return to local mode.

## Verify and stop

- Check the app URL loads and `https://<hostname>:8443/` returns the backend health message.
- Verify login, a small recording/upload, and a download from the second device.
- Use `tailscale ping <other-device>` to see whether the connection becomes direct.
  Tailscale speed depends on direct versus relayed connectivity and the internet
  links; it does not accelerate Whisper inference.
- Stop each server with Ctrl+C in its terminal.

To remove only these sharing endpoints (without resetting other Serve routes):

```powershell
& "$env:ProgramFiles\Tailscale\tailscale.exe" serve --https=443 off
& "$env:ProgramFiles\Tailscale\tailscale.exe" serve --https=8443 off
```

References: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve),
[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve).
