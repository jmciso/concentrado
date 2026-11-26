"""UI strings. To add a language: copy the "en" block, translate it, and add content/<code>/."""

import locale
import os

LANGUAGES = [("en", "English"), ("pt", "Português")]

STRINGS = {
    "en": {
        "phase.focus": "Focus",
        "phase.short": "Short break",
        "phase.long": "Long break",
        "activity.alternate": "Alternate exercise and language",
        "activity.exercise": "Exercise / stretching only",
        "activity.language": "Language lesson only",
        "activity.random": "Random",
        "activity.rest": "Just rest",
        "duration": "{m} min {s:02d} s",
        "duration.short": "{s} s",
        # overlay
        "overlay.title": "Tomate: break",
        "overlay.long_msg": "Long break. You've earned it! Really get away from your desk.",
        "overlay.short_msgs": [
            "Get up from your desk. Your body will thank you.",
            "Time to move! Step away from the screen for a few minutes.",
            "Break! Stand up before anything else.",
            "The best ideas show up away from the keyboard.",
        ],
        "overlay.add_minute": "+1 min",
        "overlay.end_break": "End break  ⏭",
        "overlay.hide": "Hide (Esc)",
        "overlay.close_tip": "Close (Esc). The break keeps counting in the top bar",
        "overlay.over": "BREAK OVER",
        "overlay.ready": "Ready to get back to focus?",
        "overlay.start_focus": "▶  Start focus",
        "overlay.close": "Close",
        # exercise
        "ex.header": "CHALLENGE · {kind} · {duration}",
        "ex.start": "▶  Start challenge",
        "ex.done": "Done! 💪  Nice work.",
        # lesson
        "lesson.header": "{flag}  MINI LESSON · {language}",
        "lesson.quiz": "Take the quiz  ▶",
        "quiz.header": "QUIZ · QUESTION {n}/{total}",
        "quiz.meaning": "What does “{term}” mean?",
        "quiz.say": "How do you say “{translation}” in {language}?",
        "quiz.score": "{emoji}  You got {score} out of {total}",
        "quiz.perfect": "Perfect!",
        "quiz.good": "Well done!",
        "quiz.retry": "This lesson will come back later so you can review it.",
        "quiz.review": "Review lesson",
        # rest
        "rest.suggestions": "SUGGESTIONS",
        "rest.rest": "REST",
        "rest.short": "Stand up, stretch and look away from the screen.",
        "rest.ideas": [
            "Go outside and walk for a few minutes.",
            "Make a healthy snack and eat it away from the screen.",
            "Drink a big glass of water.",
            "Lie on the floor and stretch out, arms overhead.",
            "Call someone you like.",
            "Open the window and look into the distance.",
        ],
        # main window
        "win.settings": "Settings",
        "win.reset_tip": "Restart this phase",
        "win.skip_tip": "Skip to the next phase",
        "win.paused_suffix": " · PAUSED",
        "win.today": "Today: {n} pomodoro{plural} 🍅",
        "btn.start": "Start",
        "btn.pause": "Pause",
        "btn.resume": "Resume",
        # settings
        "set.title": "Settings",
        "set.cancel": "Cancel",
        "set.save": "Save",
        "set.periods": "Periods (minutes)",
        "set.focus": "Focus",
        "set.short": "Short break",
        "set.long": "Long break",
        "set.cycles": "Focus sessions before a long break",
        "set.behaviour": "Behaviour",
        "set.auto_breaks": "Start breaks automatically",
        "set.auto_focus": "Start focus automatically after a break",
        "set.overlay_short": "Break screen on short breaks",
        "set.overlay_long": "Break screen on long breaks",
        "set.sound": "Sounds",
        "set.tray_label": "Show the time in the top bar",
        "set.short_breaks": "Short breaks",
        "set.activity": "Activity",
        "set.learn": "Language to learn",
        "set.system": "System",
        "set.ui_language": "App language",
        "set.autostart": "Start with the session",
        # tray
        "tray.state.running": "running",
        "tray.state.stopped": "stopped",
        "tray.state.paused": "paused",
        "tray.skip": "Skip to next phase",
        "tray.reset": "Restart phase",
        "tray.show_break": "Show break screen",
        "tray.open": "Open window",
        "tray.settings": "Settings…",
        "tray.quit": "Quit",
        # notifications
        "notify.break_over": "Break over",
        "notify.back": "Back to focus.",
        "notify.press_start": "Press Start when you're ready.",
        "notify.break_time": "Break time! 🍅",
        "notify.break_body": "{phase}, {mins} min. Get up from your desk.",
        "notify.still_running": "Tomate is still running",
        "notify.still_running_body": "It's in the top bar. Use Quit in its menu to close it.",
    },
    "pt": {
        "phase.focus": "Foco",
        "phase.short": "Pausa curta",
        "phase.long": "Pausa longa",
        "activity.alternate": "Alternar exercício e língua",
        "activity.exercise": "Só exercício / alongamento",
        "activity.language": "Só lição de línguas",
        "activity.random": "Aleatório",
        "activity.rest": "Só descansar",
        "duration": "{m} min {s:02d} s",
        "duration.short": "{s} s",
        "overlay.title": "Tomate: pausa",
        "overlay.long_msg": "Pausa longa. Mereceste! Sai mesmo da secretária.",
        "overlay.short_msgs": [
            "Levanta-te da secretária. O teu corpo agradece.",
            "Hora de mexer! Afasta-te do ecrã por uns minutos.",
            "Pausa! Põe-te de pé antes de mais nada.",
            "As melhores ideias aparecem longe do teclado.",
        ],
        "overlay.add_minute": "+1 min",
        "overlay.end_break": "Terminar pausa  ⏭",
        "overlay.hide": "Esconder (Esc)",
        "overlay.close_tip": "Fechar (Esc). A pausa continua a contar na barra",
        "overlay.over": "PAUSA TERMINADA",
        "overlay.ready": "Pronto para voltar ao foco?",
        "overlay.start_focus": "▶  Começar foco",
        "overlay.close": "Fechar",
        "ex.header": "DESAFIO · {kind} · {duration}",
        "ex.start": "▶  Começar desafio",
        "ex.done": "Feito! 💪  Bom trabalho.",
        "lesson.header": "{flag}  MINI-LIÇÃO · {language}",
        "lesson.quiz": "Fazer o quiz  ▶",
        "quiz.header": "QUIZ · PERGUNTA {n}/{total}",
        "quiz.meaning": "O que significa «{term}»?",
        "quiz.say": "Como se diz «{translation}» em {language}?",
        "quiz.score": "{emoji}  Acertaste {score} de {total}",
        "quiz.perfect": "Perfeito!",
        "quiz.good": "Muito bem!",
        "quiz.retry": "Esta lição volta a aparecer mais à frente para reveres.",
        "quiz.review": "Rever lição",
        "rest.suggestions": "SUGESTÕES",
        "rest.rest": "DESCANSA",
        "rest.short": "Levanta-te, espreguiça-te e afasta os olhos do ecrã.",
        "rest.ideas": [
            "Sai de casa ou do escritório e caminha uns minutos.",
            "Prepara um lanche saudável e come-o longe do ecrã.",
            "Bebe um copo de água grande.",
            "Deita-te no chão e estica-te, braços acima da cabeça.",
            "Liga a alguém de quem gostas.",
            "Abre a janela e olha para longe.",
        ],
        "win.settings": "Definições",
        "win.reset_tip": "Recomeçar esta fase",
        "win.skip_tip": "Saltar para a fase seguinte",
        "win.paused_suffix": " · EM PAUSA",
        "win.today": "Hoje: {n} pomodoro{plural} 🍅",
        "btn.start": "Iniciar",
        "btn.pause": "Pausar",
        "btn.resume": "Continuar",
        "set.title": "Definições",
        "set.cancel": "Cancelar",
        "set.save": "Guardar",
        "set.periods": "Períodos (minutos)",
        "set.focus": "Foco",
        "set.short": "Pausa curta",
        "set.long": "Pausa longa",
        "set.cycles": "Focos até à pausa longa",
        "set.behaviour": "Comportamento",
        "set.auto_breaks": "Iniciar pausas automaticamente",
        "set.auto_focus": "Iniciar foco automaticamente após a pausa",
        "set.overlay_short": "Ecrã de pausa nas pausas curtas",
        "set.overlay_long": "Ecrã de pausa nas pausas longas",
        "set.sound": "Sons",
        "set.tray_label": "Mostrar o tempo na barra superior",
        "set.short_breaks": "Pausas curtas",
        "set.activity": "Atividade",
        "set.learn": "Língua a aprender",
        "set.system": "Sistema",
        "set.ui_language": "Idioma da app",
        "set.autostart": "Arrancar com a sessão",
        "tray.state.running": "a contar",
        "tray.state.stopped": "parado",
        "tray.state.paused": "em pausa",
        "tray.skip": "Saltar para a fase seguinte",
        "tray.reset": "Recomeçar fase",
        "tray.show_break": "Mostrar ecrã de pausa",
        "tray.open": "Abrir janela",
        "tray.settings": "Definições…",
        "tray.quit": "Sair",
        "notify.break_over": "Pausa terminada",
        "notify.back": "De volta ao foco.",
        "notify.press_start": "Carrega em Iniciar quando estiveres pronto.",
        "notify.break_time": "Hora da pausa! 🍅",
        "notify.break_body": "{phase} de {mins} min. Levanta-te da secretária.",
        "notify.still_running": "O Tomate continua a correr",
        "notify.still_running_body": "Está na barra superior. Usa Sair no menu para o fechar.",
    },
}

_current = "en"


def system_language():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            code = value.split(":")[0][:2].lower()
            return code if code in STRINGS else "en"
    code = (locale.getlocale()[0] or "en")[:2].lower()
    return code if code in STRINGS else "en"


def set_language(code):
    global _current
    _current = code if code in STRINGS else "en"


def current():
    return _current


def t(key, **kwargs):
    value = STRINGS[_current].get(key, STRINGS["en"].get(key, key))
    return value.format(**kwargs) if kwargs and isinstance(value, str) else value
