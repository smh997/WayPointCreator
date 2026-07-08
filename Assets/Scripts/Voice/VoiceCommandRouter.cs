using UnityEngine;
using TMPro;

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
