// Авто-извлечено из main.js — чистые константы (без зависимостей).

    export const PRO_ALLOWED_EVENT_TYPES = new Set([
      "child_birth",
      "marriage_start",
      "divorce_separation",
      "death_father",
      "death_mother",
      "death_child",
      "death_spouse",
      "death_sibling",
      "death_grandparent",
      "death_close_person_other",
      "surgery",
      "major_accident",
      "violence_trauma",
      "imprisonment",
      "military_service",
      "long_hospitalization",
      "local_relocation",
      "long_distance_relocation",
      "job_start",
      "job_loss",
      "career_change",
      "profession_change",
      "business_start",
      "business_loss",
      "children_birth",
      "death_of_close_person",
      "surgery_accident_life_risk",
      "marriage_relationship",
      "relocation_emigration",
      "education_work_start",
      "profession_lifestyle_change",
      "freedom_restriction",
      "financial_rise_fall",
      "inner_crisis_turning_point",
      "custom_major_event",
    ]);

    export const PRO_ALLOWED_DATE_PRECISION = new Set(["exact", "month", "year", "range", "unknown"]);

    export const PRO_ALLOWED_REVERSIBILITY = new Set(["reversible", "irreversible", "unknown"]);

    export const PRO_ALLOWED_LIFE_AREAS = new Set(["family", "relationships", "career", "home", "health", "finance", "identity", "other"]);

    export const PRO_METHOD_LABELS = {
      directions: "Дирекции",
      solars: "Соляр",
      solar: "Соляр",
      transits: "Транзиты",
      lunars: "Лунар",
      lunar: "Лунар",
      totems: "Тотем",
      totem: "Тотем",
    };

    export const PRO_EVENT_TYPE_LABELS = {
      child_birth: "Рождение ребёнка",
      marriage_start: "Брак/союз",
      divorce_separation: "Развод/расставание",
      death_father: "Смерть отца",
      death_mother: "Смерть матери",
      death_child: "Смерть ребёнка",
      death_spouse: "Смерть супруга",
      death_sibling: "Смерть брата/сестры",
      death_grandparent: "Смерть бабушки/дедушки",
      death_close_person_other: "Смерть близкого",
      surgery: "Операция",
      major_accident: "Серьёзная авария",
      violence_trauma: "Травма/насилие",
      imprisonment: "Ограничение свободы",
      military_service: "Военная служба",
      long_hospitalization: "Длительная госпитализация",
      local_relocation: "Ближний переезд",
      long_distance_relocation: "Дальний переезд",
      job_start: "Начало работы",
      job_loss: "Потеря работы",
      career_change: "Смена карьеры",
      profession_change: "Смена профессии",
      business_start: "Старт бизнеса",
      business_loss: "Потеря бизнеса",
      financial_rise_fall: "Финансовый перелом",
      inner_crisis_turning_point: "Внутренний кризис",
      custom_major_event: "Другое важное событие",
    };

