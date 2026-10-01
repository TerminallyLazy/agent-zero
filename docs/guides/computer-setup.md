# Connect your computer

Start in the WebUI's **Connect your computer** menu, the iOS Computer screen,
or the computer icon beside an Instance in Launcher. No phone, active chat or
model configuration is required.

1. Install [Launcher](https://github.com/agent0ai/a0-launcher/releases/latest) on
   the computer A0 should use. Connect to your existing server and sign in, or
   create a local instance with Launcher's runtime setup. Remote servers do not
   require Docker on this computer.
2. Open its Instance and computer icon. Choose **Use my browser**, **Use my
   computer**, or both, then **Allow selected access**. New guided setup leaves
   files and commands off; existing permissions stay as saved.
3. Follow the current permission or preparation step. Safari requires remote
   automation; Chromium may ask for remote debugging. On macOS, approve
   Accessibility before Screen Recording. Return after each prompt so Launcher
   can check again. Other systems show their own desktop permission prompts.
4. Use **Test browser** to check typing/capture on a temporary page, or **Test
   computer** to check capture without sending input to another app. Tests
   refuse to run during host activity or a viewer hold.
5. Choose the host browser in WebUI Browser settings for tasks that must use
   this computer. Project settings can override the server default.

To continue from another device, create a setup code in the WebUI or iOS app.
On the target computer, **Open Launcher on this computer** opens setup in a
compatible packaged Launcher. If nothing opens, install/update Launcher or open
it manually. The app link carries no code, credentials or permission grant.
Sign in to the same server in Launcher and enter the code under its computer
icon. Confirm the computer name on the original device, then review access
locally. Codes expire after ten minutes and grant no permissions. Check again
reads uncertain requests without repeating them. Forgetting removes the local
record; the server code still expires automatically.

Use **Show me how** for the current step. Keep the Instance open and the computer
awake. This version requires one connected host; disconnect extra hosts if
prompted. Prepared means configured; Tested requires evidence from the last
five minutes. Computer capture does not prove desktop input. Older components
retain local Host access settings and explain which shared features need updates.

Setup never resumes A0. Take over pauses host actions; Return to A0 hands
control back. Inspect the host before clearing an uncertain-action receipt.

## Sign-in, tunnels and locked computers

A tunnel provides the connection to your server. Agent Zero's **UI Login** and
**UI Password** protect the WebUI behind it. Keep both configured when sharing
remote access. A persistent Microsoft Dev Tunnel address does not make the
Agent Zero login session permanent. Tunnel-provider authentication is separate.

Launcher can offer to save credentials after a successful sign-in. Choosing
this uses the operating system's secure storage and lets Launcher recover an
expired Agent Zero session while the credentials remain valid and storage is
available. Saving is optional; never send a password through a setup code.

Tunnels do not require locking the computer. If a new sign-in or system unlock
is required, complete it on that computer; the iOS app cannot unlock it.
Computer Use may be unavailable on a locked desktop. An offline gateway alone
cannot distinguish a locked computer, expired login, closed Launcher or sleep.
Reconnect does not clear a host-action hold. Apple's iPhone Mirroring requires
the **iPhone** to be locked; using the native Agent Zero iOS app does not.
