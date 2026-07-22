using UnityEngine;
using TMPro;

/// <summary>
/// Deserialization target for the NLU server's `command` object
/// (Server/nlu_server.py). Field types match what JsonUtility can handle --
/// `reference` is always a string (or null) on the wire, never a bare int,
/// because JsonUtility can't deserialize a polymorphic field. See
/// Server/nlu_server.py's shape_command_for_wire for the encoding.
/// </summary>
[System.Serializable]
public class NluCommand
{
    public string type;       // "authoring" | "navigation" | "execution" | "reject"
    public string operation;  // authoring: "create" | "delete" | "offset" | "delete_all"
    public string reference;  // authoring: "last", a 1-indexed integer as a string, or null
    public string axis;       // authoring offset: "x" | "y" | "z" | "rx" | "ry" | "rz"
    public float offset;      // authoring offset: meters (x/y/z) or radians (rx/ry/rz)
    public string intent;     // navigation: "configure" | "trajectory" | "preview" | "run" | "exit" | "create_mode" | "edit_mode" | "delete_mode"
    public string verb;       // execution: "run" | "confirm" | "cancel" | "stop"
    public float confidence;
}

/// <summary>
/// Central dispatcher for voice input. Maps a small set of intents onto the
/// EXISTING MenuManager / WaypointManager methods in this project. Contains no
/// robot logic of its own, so the OperationsManager state machine stays the single
/// source of truth.
///
/// Verified against the repo:
///   MenuManager: OnConfigurePressed, OnTrajectoryPressed, OnPreviewRunPressed,
///                OnPreviewPressed, OnRunPressed, OnRunConfirmed, OnRunCancelled,
///                OnSubCanvasExit
///   WaypointManager: SetMode(WaypointMode), DeleteAllWaypoints(), GetWaypoints()
///   OperationsManager: waypointManager (field), currentPhase (PlacementPhase)
///
/// Safety design:
///   * "run" only ARMS the gate (opens the existing run-confirm popup). It does not
///     move the arm.
///   * "confirm" fires OnRunConfirmed() ONLY while armed and before the timeout.
///   * "stop"/"halt" clears the gate and calls the emergency stop path.
/// </summary>
public class VoiceCommandRouter : MonoBehaviour
{
    public enum VoiceIntent
    {
        None,
        Configure, Trajectory, PreviewRun, Preview,
        CreateMode, EditMode, DeleteMode, DeleteAll, Exit,
        Run, Confirm, Cancel, Stop
    }

    [Header("Scene references")]
    public MenuManager menuManager;
    public OperationsManager operationsManager;   // waypointManager is read from here
    public ModeToggleController modeToggle;        // optional; keeps the mode button UI in sync
    public VoiceStopController stopController;     // optional; emergency stop

    [Header("Run gate")]
    [Tooltip("Seconds the armed 'run' stays valid before auto-expiring.")]
    public float armTimeoutSeconds = 8f;

    [Header("Feedback (optional)")]
    public TextMeshProUGUI voiceStatusText;

    private bool runArmed = false;
    private float armExpireTime = 0f;

    public bool IsRunArmed => runArmed && Time.time < armExpireTime;

    private WaypointManager Waypoints =>
        operationsManager != null ? operationsManager.waypointManager : null;

    private void Update()
    {
        if (runArmed && Time.time >= armExpireTime)
        {
            runArmed = false;
            Say("Run confirmation timed out. Say run again to retry.");
        }
    }

    /// <summary>Single entry point. Every voice engine calls this.</summary>
    public void Dispatch(VoiceIntent intent, float confidence = 1f, string raw = null)
    {
        Debug.Log($"[Voice] intent={intent} conf={confidence:0.00} raw=\"{raw}\"");

        switch (intent)
        {
            case VoiceIntent.Configure:
                menuManager.OnConfigurePressed();
                Say("Opening configure. Confirm on the panel to calibrate.");
                break;

            case VoiceIntent.Trajectory:
                menuManager.OnTrajectoryPressed();
                Say("Trajectory. Create mode active.");
                break;

            case VoiceIntent.PreviewRun:
                menuManager.OnPreviewRunPressed();
                Say("Preview and run panel open.");
                break;

            case VoiceIntent.Preview:
                menuManager.OnPreviewPressed();
                Say("Previewing on the digital twin.");
                break;

            case VoiceIntent.CreateMode:
                SetMode(WaypointMode.Create, "Create mode.");
                break;

            case VoiceIntent.EditMode:
                SetMode(WaypointMode.Edit, "Edit mode.");
                break;

            case VoiceIntent.DeleteMode:
                SetMode(WaypointMode.Delete, "Delete mode.");
                break;

            case VoiceIntent.DeleteAll:
                if (Waypoints != null) Waypoints.DeleteAllWaypoints();
                Say("All waypoints deleted.");
                break;

            case VoiceIntent.Exit:
                DisarmRun();
                menuManager.OnSubCanvasExit();
                Say("Back to main menu.");
                break;

            case VoiceIntent.Run:
                ArmRun();
                break;

            case VoiceIntent.Confirm:
                TryConfirmRun();
                break;

            case VoiceIntent.Cancel:
                DisarmRun();
                menuManager.OnRunCancelled();
                Say("Cancelled.");
                break;

            case VoiceIntent.Stop:
                DisarmRun();
                if (stopController != null) stopController.RequestStop();
                Say("Stop requested.");
                break;

            default:
                Debug.LogWarning($"[Voice] Unhandled intent: {intent}");
                break;
        }
    }

    /// <summary>Entry point for parsed NLU server commands (all four schema types).</summary>
    public void DispatchStructuredCommand(NluCommand cmd)
    {
        if (cmd == null)
        {
            Say("No command received.");
            return;
        }

        switch (cmd.type)
        {
            case "navigation":
                DispatchNavigationIntent(cmd.intent);
                break;
            case "execution":
                DispatchExecutionVerb(cmd.verb);
                break;
            case "authoring":
                DispatchAuthoring(cmd);
                break;
            case "reject":
                Say("Sorry, I didn't understand that command.");
                break;
            default:
                Debug.LogWarning($"[Voice] Unknown structured command type: {cmd.type}");
                break;
        }
    }

    // navigation.intent == "run" means "go to the preview/run screen"
    // (VoiceIntent.PreviewRun). This is a DIFFERENT action from
    // execution.verb == "run", which arms the safety-critical run gate
    // (VoiceIntent.Run). They come from different schema fields (intent vs
    // verb) -- do not collapse them by matching on the string "run" alone.
    private void DispatchNavigationIntent(string intent)
    {
        switch (intent)
        {
            case "configure":   Dispatch(VoiceIntent.Configure); break;
            case "trajectory":  Dispatch(VoiceIntent.Trajectory); break;
            case "preview":     Dispatch(VoiceIntent.Preview); break;
            case "run":         Dispatch(VoiceIntent.PreviewRun); break; // preview/run SCREEN, not the robot gate
            case "exit":        Dispatch(VoiceIntent.Exit); break;
            case "create_mode": Dispatch(VoiceIntent.CreateMode); break;
            case "edit_mode":   Dispatch(VoiceIntent.EditMode); break;
            case "delete_mode": Dispatch(VoiceIntent.DeleteMode); break;
            default:
                Debug.LogWarning($"[Voice] Unknown navigation intent: {intent}");
                break;
        }
    }

    private void DispatchExecutionVerb(string verb)
    {
        switch (verb)
        {
            case "run":     Dispatch(VoiceIntent.Run); break;     // arms the safety-critical run gate
            case "confirm": Dispatch(VoiceIntent.Confirm); break;
            case "cancel":  Dispatch(VoiceIntent.Cancel); break;
            case "stop":    Dispatch(VoiceIntent.Stop); break;
            default:
                Debug.LogWarning($"[Voice] Unknown execution verb: {verb}");
                break;
        }
    }

    private void DispatchAuthoring(NluCommand cmd)
    {
        switch (cmd.operation)
        {
            case "create":
                // Voice cannot supply a 3D point -- arm the gesture, don't invent a position.
                SetMode(WaypointMode.Create, "Create mode. Pinch to place a waypoint.");
                break;

            case "delete_all":
                if (Waypoints != null) Waypoints.DeleteAllWaypoints();
                Say("All waypoints deleted.");
                break;

            case "delete":
                HandleVoiceDelete(cmd.reference);
                break;

            case "offset":
                HandleVoiceOffset(cmd.reference, cmd.axis, cmd.offset);
                break;

            default:
                Debug.LogWarning($"[Voice] Unknown authoring operation: {cmd.operation}");
                break;
        }
    }

    // Deliberately bypasses the WaypointMode.Delete gate: RemoveWaypoint has
    // no internal mode check (the gate lives only at its two existing UI call
    // sites), and a voice `delete <reference>` already fully specifies its
    // target, so there's no missing-information reason to force a mode
    // switch first (and doing so would trigger the Delete-mode waypoint
    // recoloring as an unwanted side effect).
    private void HandleVoiceDelete(string reference)
    {
        if (Waypoints == null)
        {
            Say("No waypoints to delete.");
            return;
        }

        var result = Waypoints.TryGetWaypointByReference(reference, out Waypoint wp);
        switch (result)
        {
            case ReferenceResolution.Resolved:
                Waypoints.RemoveWaypoint(wp);
                break;
            case ReferenceResolution.Missing:
                Say("Which waypoint? Say delete last, or a waypoint number.");
                break;
            case ReferenceResolution.OutOfRange:
                Say(OutOfRangeMessage(reference));
                break;
        }
    }

    private void HandleVoiceOffset(string reference, string axis, float value)
    {
        if (Waypoints == null || operationsManager == null || operationsManager.robotBase == null)
        {
            Say("Can't apply offset right now.");
            return;
        }

        var result = Waypoints.TryGetWaypointByReference(reference, out Waypoint wp);
        if (result == ReferenceResolution.Missing)
        {
            Say("Which waypoint? Say offset last, or a waypoint number.");
            return;
        }
        if (result == ReferenceResolution.OutOfRange)
        {
            Say(OutOfRangeMessage(reference));
            return;
        }

        var offsetResult = Waypoints.TryApplyOffset(wp, axis, value, operationsManager.robotBase);
        Say(offsetResult == OffsetResult.UnsupportedAxis
            ? "Rotation offsets aren't wired up yet."
            : "Offset applied.");
    }

    // ---- run gate ----

    private void ArmRun()
    {
        // Only meaningful on the Preview/Run screen with waypoints present.
        if (Waypoints == null || Waypoints.GetWaypoints().Count == 0)
        {
            Say("No waypoints to run.");
            return;
        }

        menuManager.OnRunPressed();   // shows the existing run-confirm popup
        runArmed = true;
        armExpireTime = Time.time + armTimeoutSeconds;
        Say("Ready to run on the real robot. Say confirm to execute, or cancel.");
    }

    private void TryConfirmRun()
    {
        if (!IsRunArmed)
        {
            Say("Nothing to confirm. Say run first.");
            return;
        }
        runArmed = false;
        menuManager.OnRunConfirmed();  // sets previewAction = Run -> server run
        Say("Confirmed. Executing trajectory on the real robot.");
    }

    private void DisarmRun() => runArmed = false;

    private string OutOfRangeMessage(string reference) =>
        reference == "last" ? "There are no waypoints." : $"There's no waypoint {reference}.";

    private void SetMode(WaypointMode mode, string msg)
    {
        // Prefer the UI controller so the mode button label/color stays in sync.
        // Fall back to setting the mode directly if the controller isn't wired
        // (e.g. on a screen without the mode button).
        if (modeToggle != null)
            modeToggle.SetModeExternally(mode);
        else if (Waypoints != null)
            Waypoints.SetMode(mode);
        Say(msg);
    }

    private void Say(string message)
    {
        if (voiceStatusText != null) voiceStatusText.text = message;
        Debug.Log("[Voice] " + message);
    }
}
