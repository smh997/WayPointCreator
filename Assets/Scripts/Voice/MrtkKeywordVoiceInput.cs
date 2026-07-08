using System.Collections.Generic;
using UnityEngine;
using Microsoft.MixedReality.Toolkit;
using Microsoft.MixedReality.Toolkit.Input;

/// <summary>
/// MRTK2 keyword speech for the safety-critical + common navigation verbs.
///
/// This is the idiomatic MRTK 2.8 path: it implements IMixedRealitySpeechHandler and
/// registers for global speech events, rather than using UnityEngine's raw
/// KeywordRecognizer. Recognition runs on-device on the HoloLens 2, offline.
///
/// SETUP (one-time, required) — the keywords below must ALSO be added to the MRTK
/// Speech Command Profile, or MRTK will never raise them:
///   MRTK GameObject -> Input -> Speech -> (clone the profile) -> add each keyword
///   phrase EXACTLY as written in the KeywordMap keys (case-insensitive match here).
/// You do NOT need to set a KeywordAction there; this handler dispatches by phrase.
///
/// Microphone capability is already enabled in this project.
/// </summary>
public class MrtkKeywordVoiceInput : MonoBehaviour, IMixedRealitySpeechHandler
{
    [Header("Router")]
    public VoiceCommandRouter router;

    // Phrase (lower-case) -> intent. Add the SAME phrases to the MRTK Speech profile.
    private readonly Dictionary<string, VoiceCommandRouter.VoiceIntent> keywordMap =
        new Dictionary<string, VoiceCommandRouter.VoiceIntent>()
    {
        // run gate
        { "run",            VoiceCommandRouter.VoiceIntent.Run },
        { "run it",         VoiceCommandRouter.VoiceIntent.Run },
        { "send to robot",  VoiceCommandRouter.VoiceIntent.Run },
        { "confirm",        VoiceCommandRouter.VoiceIntent.Confirm },
        { "confirm run",    VoiceCommandRouter.VoiceIntent.Confirm },
        { "cancel",         VoiceCommandRouter.VoiceIntent.Cancel },
        { "abort",          VoiceCommandRouter.VoiceIntent.Cancel },

        // emergency — multiple phrasings so it always catches
        { "stop",           VoiceCommandRouter.VoiceIntent.Stop },
        { "halt",           VoiceCommandRouter.VoiceIntent.Stop },
        { "stop the robot", VoiceCommandRouter.VoiceIntent.Stop },
        { "emergency stop", VoiceCommandRouter.VoiceIntent.Stop },

        // navigation / authoring
        { "configure",      VoiceCommandRouter.VoiceIntent.Configure },
        { "trajectory",     VoiceCommandRouter.VoiceIntent.Trajectory },
        { "preview run",    VoiceCommandRouter.VoiceIntent.PreviewRun },
        { "preview",        VoiceCommandRouter.VoiceIntent.Preview },
        { "create mode",    VoiceCommandRouter.VoiceIntent.CreateMode },
        { "edit mode",      VoiceCommandRouter.VoiceIntent.EditMode },
        { "delete mode",    VoiceCommandRouter.VoiceIntent.DeleteMode },
        { "delete all",     VoiceCommandRouter.VoiceIntent.DeleteAll },
        { "exit",           VoiceCommandRouter.VoiceIntent.Exit },
        { "go back",        VoiceCommandRouter.VoiceIntent.Exit },
    };

    private void OnEnable()
    {
        // Register for global speech events so keywords work regardless of focus.
        CoreServices.InputSystem?.RegisterHandler<IMixedRealitySpeechHandler>(this);
    }

    private void OnDisable()
    {
        CoreServices.InputSystem?.UnregisterHandler<IMixedRealitySpeechHandler>(this);
    }

    void IMixedRealitySpeechHandler.OnSpeechKeywordRecognized(SpeechEventData eventData)
    {
        if (router == null) return;

        string phrase = eventData.Command.Keyword.ToLowerInvariant().Trim();
        if (keywordMap.TryGetValue(phrase, out var intent))
        {
            router.Dispatch(intent, 1f, phrase);
        }
        else
        {
            Debug.Log($"[MrtkKeyword] Unmapped keyword heard: \"{phrase}\"");
        }
    }
}
