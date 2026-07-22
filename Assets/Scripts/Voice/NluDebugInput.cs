using System.IO;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

/// <summary>
/// Editor-only debug input for Stage 1 NLU pipeline testing (no HoloLens
/// dictation -- that's Stage 2). Sends an utterance to the standalone NLU
/// server (Server/nlu_server.py, 127.0.0.1:5001) and dispatches the parsed
/// command through VoiceCommandRouter.
///
/// Self-bootstraps at Play-mode start -- no scene/prefab/Inspector wiring
/// required. Never compiled into the HoloLens release build.
/// </summary>
public class NluDebugInput : MonoBehaviour
{
#if UNITY_EDITOR || DEVELOPMENT_BUILD
    private const string ServerIP = "127.0.0.1";
    private const int ServerPort = 5001;

    // Covers all four schema types plus one reject case, for one-key smoke testing.
    private static readonly string[] CannedUtterances =
    {
        "move waypoint two up five centimeters", // authoring / offset
        "delete the last waypoint",               // authoring / delete
        "go to configure",                        // navigation
        "run it",                                 // execution
        "what's the weather today",                // reject
    };

    private string inputText = "";
    private string statusText = "";
    private VoiceCommandRouter router;
    private WaypointManager waypointManager;
    private OperationsManager operationsManager;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void Bootstrap()
    {
        var go = new GameObject("[NluDebugInput]");
        go.AddComponent<NluDebugInput>();
        DontDestroyOnLoad(go);
    }

    private void Start()
    {
        router = FindObjectOfType<VoiceCommandRouter>();
        if (router == null)
            Debug.LogWarning("[NluDebugInput] No VoiceCommandRouter found in scene -- " +
                              "responses will be logged but not dispatched.");

        waypointManager = FindObjectOfType<WaypointManager>();
        operationsManager = FindObjectOfType<OperationsManager>();
    }

    private void Update()
    {
        if (GUI.GetNameOfFocusedControl() == "NluTextField")
            return;

        if (Input.GetKeyDown(KeyCode.Alpha0))
        {
            SpawnDebugWaypoint();
            return;
        }

        for (int i = 0; i < CannedUtterances.Length; i++)
        {
            if (Input.GetKeyDown(KeyCode.Alpha1 + i))
                SendUtterance(CannedUtterances[i]);
        }
    }

    // Bypasses MRTK hand-pinch placement for manual testing convenience: places
    // a waypoint at a fixed point in front of and slightly above the robot base
    // (robotBase-local space), so voice/authoring commands have something to
    // target without simulating a pinch first.
    private void SpawnDebugWaypoint()
    {
        if (waypointManager == null || operationsManager == null || operationsManager.robotBase == null)
        {
            Debug.LogWarning("[NluDebugInput] Can't spawn a debug waypoint -- " +
                              "WaypointManager/OperationsManager/robotBase not found.");
            return;
        }

        Transform robotBase = operationsManager.robotBase;
        Vector3 localSpawnPos = new Vector3(0f, 0.2f, 0.4f);
        Vector3 worldSpawnPos = robotBase.TransformPoint(localSpawnPos);

        waypointManager.SetMode(WaypointMode.Create);
        waypointManager.AddWaypoint(worldSpawnPos, robotBase.rotation);
        Debug.Log($"[NluDebugInput] Spawned debug waypoint at robotBase-local {localSpawnPos} (world {worldSpawnPos}).");
    }

    private void OnGUI()
    {
        GUILayout.BeginArea(new Rect(10, 10, 420, 150));
        GUILayout.Label("NLU Debug Input  (key 0 = spawn waypoint, keys 1-5 = canned utterances)");
        GUI.SetNextControlName("NluTextField");
        inputText = GUILayout.TextField(inputText);

        bool enterPressed = Event.current.type == EventType.KeyDown &&
                             Event.current.keyCode == KeyCode.Return;
        if (GUILayout.Button("Send") || enterPressed)
            SendUtterance(inputText);

        GUILayout.Label(statusText);
        GUILayout.EndArea();
    }

    private void ReportServerUnreachable(System.Exception e)
    {
        statusText = $"NLU server not reachable on {ServerIP}:{ServerPort}";
        Debug.LogWarning("[NluDebugInput] " + statusText + " (" + e.Message + ")");
    }

    private void SendUtterance(string utterance)
    {
        if (string.IsNullOrEmpty(utterance)) return;
        statusText = $"Sending: \"{utterance}\"...";

        try
        {
            using (TcpClient client = new TcpClient(ServerIP, ServerPort))
            using (NetworkStream stream = client.GetStream())
            {
                string json = "{\"type\":\"nlu\",\"utterance\":\"" + EscapeJson(utterance) + "\"}\n";
                byte[] data = Encoding.UTF8.GetBytes(json);
                stream.Write(data, 0, data.Length);

                byte[] buffer = new byte[4096];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                string response = Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
                statusText = response;
                Debug.Log("[NluDebugInput] Response: " + response);

                var parsed = JsonUtility.FromJson<NluServerResponse>(response);
                if (parsed != null && parsed.success && router != null)
                    router.DispatchStructuredCommand(parsed.command);
            }
        }
        catch (SocketException e)
        {
            ReportServerUnreachable(e);
        }
        catch (IOException e)
        {
            ReportServerUnreachable(e);
        }
    }

    private static string EscapeJson(string s) => s.Replace("\\", "\\\\").Replace("\"", "\\\"");
#endif
}

#if UNITY_EDITOR || DEVELOPMENT_BUILD
[System.Serializable]
public class NluServerResponse
{
    public bool success;
    public string message;
    public NluCommand command;
}
#endif
