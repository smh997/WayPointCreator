using System;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

/// <summary>
/// Emergency stop. Sends {"type":"stop"} to the server on a fresh, short-lived TCP
/// connection (dedicated stop port), so it is not queued behind the blocking "run"
/// on the main OperationsManager connection.
///
/// Requires the server-side stop listener (see server.py patch). If you have NOT
/// added the server patch yet, leave stopController unassigned on the router and the
/// "stop" keyword will simply log — wire this once the server side is ready.
///
/// A software voice-stop is a convenience layer, NOT a replacement for the robot's
/// hardware e-stop. Keep the physical e-stop reachable at all times.
/// </summary>
public class VoiceStopController : MonoBehaviour
{
    [Header("Networking")]
    public string serverIP = "192.168.0.100";
    [Tooltip("Dedicated stop-listener port on the server (STOP_PORT in server.py).")]
    public int serverPort = 5002;
    public int timeoutMs = 1500;

    public void RequestStop()
    {
        Debug.LogWarning("[VoiceStop] STOP requested by voice.");
        new Thread(SendStopBlocking) { IsBackground = true }.Start();
    }

    private void SendStopBlocking()
    {
        try
        {
            using (TcpClient client = new TcpClient())
            {
                var ar = client.BeginConnect(serverIP, serverPort, null, null);
                if (!ar.AsyncWaitHandle.WaitOne(timeoutMs))
                {
                    Debug.LogError("[VoiceStop] Connect timed out.");
                    return;
                }
                client.EndConnect(ar);

                using (NetworkStream stream = client.GetStream())
                {
                    stream.WriteTimeout = timeoutMs;
                    stream.ReadTimeout = timeoutMs;
                    byte[] msg = Encoding.UTF8.GetBytes("{\"type\":\"stop\"}\n");
                    stream.Write(msg, 0, msg.Length);

                    byte[] buf = new byte[512];
                    try
                    {
                        int n = stream.Read(buf, 0, buf.Length);
                        if (n > 0)
                            Debug.Log("[VoiceStop] Server: " + Encoding.UTF8.GetString(buf, 0, n).Trim());
                    }
                    catch { /* response optional; stop already sent */ }
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError("[VoiceStop] Failed to send stop: " + e.Message);
        }
    }
}
