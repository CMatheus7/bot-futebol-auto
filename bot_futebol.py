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
import sys

# === CONFIGURAÇÕES ===
# Verifica se está rodando no GitHub Actions
IS_GITHUB_ACTIONS = os.getenv('GITHUB_ACTIONS') == 'true'

# Configurações (usando variáveis de ambiente com fallback para valores locais)
API_KEY = os.getenv('API_KEY', '725ec13647cb4c8fb762c0703b231011')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '7493774591:AAH1lKcP6JBDxTecfKS9bmyfnZkLOZ2GWh4')
CHAT_ID = os.getenv('CHAT_ID', '-1002672810278')
API_URL = os.getenv('API_URL', "https://api.football-data.org/v4")

headers = {'X-Auth-Token': API_KEY}
fuso_brasil = pytz.timezone('America/Sao_Paulo')

# Configuração de log diferenciada para GitHub Actions
if IS_GITHUB_ACTIONS:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(f"log_{datetime.now(fuso_brasil).strftime('%d-%m-%Y')}.txt"),
            logging.StreamHandler()
        ]
    )


# ===== BANDEIRAS DAS LIGAS =====
BANDERAS_LIGAS = {
    'Serie A': '🇮🇹', 'Premier League': '🏴', 'Eredivisie': '🇳🇱',
    'Bundesliga': '🇩🇪', 'Ligue 1': '🇫🇷', 'Primeira Liga': '🇵🇹',
    'Campeonato Brasileiro Série A': '🇧🇷', 'La Liga': '🇪🇸',
    'Championship': '🏴', 'Liga Profesional de Fútbol': '🇦🇷',
    'Major League Soccer': '🇺🇸', 'J1 League': '🇯🇵', 'Süper Lig': '🇹🇷',
    'Russian Premier League': '🇷🇺', 'Belgian Pro League': '🇧🇪',
    'Swiss Super League': '🇨🇭', 'Scottish Premiership': '🏴',
    'Superliga Argentina': '🇦🇷', 'Liga MX': '🇲🇽', 'Serie B': '🇮🇹',
    'Segunda División': '🇪🇸', 'Brasileirão Série B': '🇧🇷', 'Liga Portugal 2': '🇵🇹',
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
    """Salva uma mensagem de log no arquivo do dia."""
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
    print(f"Horário no Brasil: {agora.strftime('%d/%m/%Y %H:%M')}")
    if agora.hour >= 21:
        data_ref = agora + timedelta(days=1)
        descricao = "amanhã"
    else:
        data_ref = agora
        descricao = "hoje"
    print(f"Buscando jogos de {descricao} ({data_ref.strftime('%d/%m/%Y')})")
    return data_ref, descricao

def ler_csv_existente(caminho_csv):
    """Lê o CSV existente para evitar duplicidade de jogos."""
    jogos_existentes = set()
    if os.path.exists(caminho_csv):
        with open(caminho_csv, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)
            for row in reader:
                liga, hora, home, away = row
                jogos_existentes.add((liga, hora.strip(), home.strip(), away.strip()))
    return jogos_existentes

def gerar_csv_jogos(jogos_por_liga, data_hoje):
    """Gera ou atualiza um arquivo CSV com os jogos interessantes."""
    caminho_csv = f"jogos_{data_hoje.replace('/', '-')}.csv"
    jogos_existentes = ler_csv_existente(caminho_csv)
    novos_jogos = 0

    with open(caminho_csv, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if file.tell() == 0:
            writer.writerow(["Liga", "Hora", "Time da Casa", "Time Visitante"])

        for liga, jogos in jogos_por_liga.items():
            for jogo in jogos:
                hora, teams = jogo.split(" - ")
                home, away = teams.replace("*", "").split(" 🆚 ")
                if (liga, hora.strip(), home.strip(), away.strip()) not in jogos_existentes:
                    writer.writerow([liga, hora.strip(), home.strip(), away.strip()])
                    jogos_existentes.add((liga, hora.strip(), home.strip(), away.strip()))
                    novos_jogos += 1

    print(f"✅ CSV atualizado: {caminho_csv} | {novos_jogos} novos jogos adicionados")
    salvar_log(f"CSV atualizado com {novos_jogos} novos jogos")
    return caminho_csv

def get_jogos_do_dia(data_api):
    """Busca os jogos do dia através da API."""
    url = f'{API_URL}/matches?date={data_api}'
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        jogos = data.get('matches', [])
        jogos_por_liga = defaultdict(list)

        for match in jogos:
            if match.get('status', '') == 'FINISHED':
                continue  # Ignora jogos já finalizados
            liga = match['competition']['name']
            utc_time = match['utcDate']
            horario_utc = datetime.fromisoformat(utc_time.replace('Z', '+00:00')).replace(tzinfo=pytz.UTC)
            horario_brasil = horario_utc.astimezone(fuso_brasil)
            hora_formatada = horario_brasil.strftime('%H:%M')
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            linha = f"{hora_formatada} - *{home}* 🆚 *{away}*"
            jogos_por_liga[liga].append(linha)

        salvar_log(f"API retornou {len(jogos)} jogos")
        return jogos_por_liga
    else:
        salvar_log(f"Erro API {response.status_code}: {response.text}")
        print(f"Erro ao acessar a API: {response.status_code}")
        return {}

def montar_mensagem_formatada(jogos_por_liga, descricao_data):
    """Monta a mensagem que será enviada para o Telegram."""
    mensagem = f"📅 *CSBOT*\n*Jogos em destaque {descricao_data}:*\n\n"
    encontrou_jogos = False

    for liga, jogos in jogos_por_liga.items():
        jogos_interessantes = []
        for jogo in sorted(jogos):
            hora, teams = jogo.split(" - ")
            home, away = teams.replace("*", "").split(" 🆚 ")
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
    """Envia a mensagem formatada para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': mensagem,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("✅ Mensagem enviada para o Telegram com sucesso!")
        salvar_log("Mensagem enviada para o Telegram")
    else:
        print("Erro ao enviar mensagem para o Telegram:", response.text)
        salvar_log(f"Erro ao enviar mensagem Telegram: {response.text}")

def tarefa_diaria():
    """Função principal que executa toda a rotina diária."""
    try:
        data_ref, descricao_data = obter_data_referencia()
        data_formatada_api = data_ref.strftime('%Y-%m-%d')
        data_formatada_csv = data_ref.strftime('%d/%m/%Y')

        jogos_por_liga = get_jogos_do_dia(data_formatada_api)

        if jogos_por_liga:
            gerar_csv_jogos(jogos_por_liga, data_formatada_csv)
            mensagem = montar_mensagem_formatada(jogos_por_liga, descricao_data)
            enviar_mensagem_telegram(mensagem)
        else:
            print("❌ Nenhum jogo encontrado para a data solicitada.")
            salvar_log("Nenhum jogo encontrado na data solicitada")

    except Exception as e:
        erro = f"❌ *Erro durante a execução:*\n`{str(e)}`"
        print(erro)
        salvar_log(erro)
        enviar_mensagem_telegram(erro)

# ===== EXECUÇÃO PRINCIPAL ===== 
if __name__ == "__main__":
    logging.info("🚀 Iniciando Bot de Futebol")
    
    if IS_GITHUB_ACTIONS:
        logging.info("🔧 Modo GitHub Actions ativado")
        # Força o fuso horário para BRT mesmo executando em UTC
        os.environ['TZ'] = 'America/Sao_Paulo'
        time.tzset()
        
        # Execução imediata e única
        tarefa_diaria()
    else:
        logging.info("⏰ Modo Render - Agendando para 7h BRT (10h UTC)")
        
        # Executa imediatamente (opcional)
        tarefa_diaria()
        
        # Configura o agendamento para 10:00 UTC (7:00 BRT)
        schedule.every().day.at("10:00").do(tarefa_diaria)
        
        # Loop principal
        while True:
            schedule.run_pending()
            
            # Verificação adicional para horário local (backup)
            agora = datetime.now(fuso_brasil)
            if agora.hour == 7 and agora.minute == 0:
                logging.info("⏰ Acionamento por horário local (7h BRT)")
                tarefa_diaria()
                time.sleep(60)  # Evita múltiplas execuções
            
            time.sleep(30)
