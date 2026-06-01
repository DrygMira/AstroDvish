// Авто-извлечено из main.js — общий мутабельный стейт приложения.

// Переприсваиваемые примитивы собраны в один объект, чтобы их можно было
// читать и менять из любого модуля (импорт-биндинги доступны только на чтение).
export const appState = {
      expertDegreesExpanded: false,
      lastExpertRenderPayload: null,
      llmOverlayTimerId: null,
      llmOverlayStartedAt: 0,
      technicalModeOpen: false,
      lastGenerateTechnicalDebug: null,
      lastGeocodeTechnicalDebug: null,
      lastProRunPayload: null,
      lastChartPromptBase: null,
      activeCoordinateInputId: null,
};

    export const rectDialogState = {
      rectificationDocument: null,
      dialogHistory: [],
      stepCount: 0,
      currentQuestion: null,
      selectedOption: null,
      lastLlmRaw: null,
      isBusy: false,
      usageSteps: [],
      usageTotal: {
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        cached_input_tokens: 0,
        reasoning_tokens: 0,
      },
    };

    export const rectEventsState = {
      dialogHistory: [],
      currentQuestion: null,
      finalized: null,
      rawLastResponse: null,
      isBusy: false,
    };

    export const rectificationWizardState = {
      birthDateLocal: null,
      birthTimeKnown: false,
      birthPlace: null,
      latitude: null,
      longitude: null,
      timezoneMode: "auto",
      timezoneName: null,
      timezoneOffset: null,
      ascIntervals: null,
      stage1: {
        started: false,
        completed: false,
        primaryCandidate: null,
        secondaryCandidates: [],
        timeRangesLocal: [],
        elementScores: null,
        modalityScores: null,
        signScores: null,
        candidateGroup: null,
        leadingElement: null,
        leadingModality: null,
        summaryText: null,
        explanationText: null,
        methodLimitations: [],
        stageWarnings: [],
      },
      stage2: {
        started: false,
        completed: false,
        events: [],
        eventCards: [],
      },
      pro: {
        started: false,
        completed: false,
        result: null,
      },
    };

    export const sharedBirthContext = {
      apiBaseUrl: "",
      birthDateLocal: null,
      birthDateTimeLocal: null,
      cityQuery: null,
      selectedPlaceLabel: null,
      latitude: null,
      longitude: null,
      timezoneMode: "auto",
      timezoneName: null,
      timezoneOffset: "+05:00",
      timezoneResolvedOffset: null,
      timezoneSource: null,
      coordValueFormat: "decimal",
      latitudeDms: null,
      longitudeDms: null,
      houseSystem: "P",
      zodiacMode: "tropical",
      siderealMode: null,
      aspectOrbProfile: "avestan",
    };
