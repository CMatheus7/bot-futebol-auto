# ===== IMPORTAÇÕES =====
from datetime import datetime, timedelta
import pytz
import requests
from collections import defaultdict
import csv
import os
import logging
import schedule
import time

# ===== CONFIGURAÇÕES GERAIS =====
# Use variáveis de ambiente para maior segurança
API_KEY = os.getenv('API_KEY', '725ec13647cb4c8fb762c0703b231011')  # Valor padrão apenas para desenvolvimento
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '7664394208:AAE-ZIWIUfAqBY47C2CSq3wnna1G8LGYuBE')
CHAT_ID = os.getenv('CHAT_ID', '-1002672810278')
API_URL = "https://api.football-data.org/v4"

# Headers da API
headers = {
    'X-Auth-Token': API_KEY
}

# Configura o fuso horário brasileiro
fuso_brasil = pytz.timezone('America/Sao_Paulo')

# Configurações de log simplificadas para o Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# ===== BANDEIRAS DAS LIGAS =====
BANDERAS_LIGAS = {
    'Serie A': '🇮🇹', 'Premier League': '🏴', 'Eredivisie': '🇳🇱',
    'Bundesliga': '🇩🇪', 'Ligue 1': '🇫🇷', 'Primeira Liga': '🇵🇹',
    'Campeonato Brasileiro Série A': '🇧🇷', 'La Liga': '🇪🇸',
    'Championship': '🏴', 'Liga Profesional de Fútbol': '🇦🇷',
    'Major League Soccer': '🇺🇸', 'J1 League': '🇯🇵', 'Süper Lig': '🇹🇷',
}

# ===== LIGAS E TIMES INTERESSANTES =====
LIGAS_OVER = [
    'Eredivisie', 'Bundesliga', 'Premier League', 'Serie A',
    'Primeira Liga', 'Major League Soccer', 'La Liga',
    'Superliga Argentina', 'Süper Lig'
]

LIGAS_BRASIL = ['Campeonato Brasileiro Série A', 'Brasileirão Série B']

FAVORITOS = [
    'PSG', 'Real Madrid', 'Barcelona', 'Bayern', 'Manchester City', 'Liverpool',
    'Ajax', 'Inter', 'Juventus', 'Benfica', 'Porto',
    'Flamengo', 'Palmeiras', 'Atlético-MG', 'Grêmio',
    'Corinthians', 'São Paulo'
]

# ===== FUNÇÕES AUXILIARES =====

def salvar_log(mensagem_log):
    """Salva uma mensagem de log."""
    logging.info(mensagem_log)

def é_jogo_interessante(liga, home, away):
    """Define se o jogo é de interesse baseado na liga ou nos times favoritos."""
    if liga in LIGAS_OVER or liga in LIGAS_BRASIL:
        return True
    for favorito in FAVORITOS:
        if favorito.lower() in home.lower() or favorito.lower() in away.lower():
            return True
    return False

def obter_data_referencia():
    """Define se deve buscar jogos de hoje ou de amanhã baseado no horário."""
    agora = datetime.now(fuso_brasil)
    salvar_log(f"Horário no Brasil: {agora.strftime('%d/%m/%Y %H:%M')}")
    if agora.hour >= 21:
        data_ref = agora + timedelta(days=1)
        descricao = "amanhã"
    else:
        data_ref = agora
        descricao = "hoje"
    salvar_log(f"Buscando jogos de {descricao} ({data_ref.strftime('%d/%m/%Y')})")
    return data_ref, descricao

def get_jogos_do_dia(data_api):
    """Busca os jogos do dia através da API."""
    url = f'{API_URL}/matches?date={data_api}'
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        jogos = data.get('matches', [])
        jogos_por_liga = defaultdict(list)

        for match in jogos:
            if match.get('status', '') == 'FINISHED':
                continue
            liga = match['competition']['name']
            utc_time = match['utcDate']
            horario_utc = datetime.fromisoformat(utc_time.replace('Z', '+00:00')).replace(tzinfo=pytz.UTC)
            horario_brasil = horario_utc.astimezone(fuso_brasil)
            hora_formatada = horario_brasil.strftime('%H:%M')
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            linha = f"{hora_formatada} - {home} 🆚 {away}"
            jogos_por_liga[liga].append(linha)

        salvar_log(f"API retornou {len(jogos)} jogos")
        return jogos_por_liga
    except Exception as e:
        salvar_log(f"Erro ao acessar API: {str(e)}")
        return {}

def montar_mensagem_formatada(jogos_por_liga, descricao_data):
    """Monta a mensagem para o Telegram."""
    mensagem = f"📅 *Jogos em destaque {descricao_data}:*\n\n"
    encontrou_jogos = False

    for liga, jogos in jogos_por_liga.items():
        jogos_interessantes = []
        for jogo in sorted(jogos):
            hora, teams = jogo.split(" - ")
            home, away = teams.split(" 🆚 ")
            if é_jogo_interessante(liga, home.strip(), away.strip()):
                jogos_interessantes.append((hora.strip(), home.strip(), away.strip()))

        if jogos_interessantes:
            bandeira = BANDERAS_LIGAS.get(liga, '🌐')
            mensagem += f"*{bandeira} {liga}*\n"
            for hora, home, away in jogos_interessantes:
                mensagem += f"🕒 {hora} - {home} x {away}\n"
            mensagem += "\n"
            encontrou_jogos = True

    if not encontrou_jogos:
        mensagem += "❌ Nenhum jogo interessante encontrado hoje.\n\n"

    mensagem += (
        "\n⚠️ *Apostas são para +18*\n"
        "🧠 *Jogue com responsabilidade*\n"
        f"_{datetime.now(fuso_brasil).strftime('%H:%M')}_"
    )
    return mensagem

def enviar_mensagem_telegram(mensagem):
    """Envia a mensagem para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': mensagem,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        salvar_log("Mensagem enviada para o Telegram com sucesso!")
    except Exception as e:
        salvar_log(f"Erro ao enviar mensagem Telegram: {str(e)}")

def tarefa_diaria():
    """Função principal que executa toda a rotina."""
    try:
        data_ref, descricao_data = obter_data_referencia()
        data_formatada_api = data_ref.strftime('%Y-%m-%d')

        jogos_por_liga = get_jogos_do_dia(data_formatada_api)

        if jogos_por_liga:
            mensagem = montar_mensagem_formatada(jogos_por_liga, descricao_data)
            enviar_mensagem_telegram(mensagem)
        else:
            salvar_log("Nenhum jogo encontrado na data solicitada")

    except Exception as e:
        erro = f"❌ Erro durante a execução: {str(e)}"
        salvar_log(erro)
        enviar_mensagem_telegram(erro)

# ===== EXECUÇÃO PRINCIPAL =====
if __name__ == "__main__":
    salvar_log("⏳ Bot iniciado!")
    
    # Executa imediatamente
    tarefa_diaria()
    
    # No Render free, o agendamento não funciona bem, então usamos um loop
    while True:
        # Verifica se é hora de executar (20:55 no horário do Render - UTC)
        agora = datetime.now(pytz.UTC)
        if agora.hour == 23 and agora.minute == 55:  # 20:55 BRT = 23:55 UTC
            tarefa_diaria()
            time.sleep(60)  # Espera 1 minuto para não executar múltiplas vezes
        time.sleep(30)  # Verifica a cada 30 segundos
