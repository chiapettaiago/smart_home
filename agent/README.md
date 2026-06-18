# Smart Home Windows Agent

Cliente Windows do sistema Casa Inteligente. O agente registra a máquina no servidor central, mantém um WebSocket autenticado, envia telemetria periódica e executa somente comandos presentes em uma whitelist.

## Recursos

- UUID persistente por máquina.
- Registro HTTP com hostname, IP, versão do Windows e arquitetura.
- WebSocket autenticado com reconexão exponencial.
- Heartbeat com CPU, RAM, disco, usuário, uptime e IP.
- Serviço Windows sem interface gráfica.
- Logs rotativos em arquivo.
- Programas, processos e hosts de URL configurados por allowlist.
- Nenhum `exec`, shell remoto ou comando arbitrário.

Comandos implementados:

- `shutdown`
- `reboot`
- `lock_screen`
- `sleep`
- `logout`
- `open_program`
- `close_program`
- `open_url`
- `get_processes`
- `get_system_info`

## Requisitos

- Windows 10 ou Windows 11.
- Python 3.12 ou superior, na mesma arquitetura do Windows.
- Conta administrativa para instalar o serviço.
- Servidor central acessível pela rede.

## Instalação

### Instalador executável

O artefato recomendado é:

```text
SmartHomeAgentSetup.exe
```

Ao executá-lo como administrador, o assistente solicita:

- URL HTTP(S) do servidor;
- URL WebSocket;
- token exclusivo do agente;
- validação TLS.

Depois ele instala os arquivos em `C:\Program Files\SmartHomeAgent`, grava a configuração em `C:\ProgramData\SmartHomeAgent` e inicia o serviço automaticamente.

Para gerar o instalador em um Windows com Python 3.12 e [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```powershell
.\agent\build\windows\build.ps1 -Clean
```

Saída:

```text
dist\windows\SmartHomeAgentSetup.exe
```

Também existe o workflow `Build Windows Agent` no GitHub Actions. Ele gera o instalador como artefato em um runner Windows.

### Instalação para desenvolvimento

Abra o PowerShell na pasta que contém este repositório:

```powershell
cd C:\caminho\smart-home-server
py -3.12 -m venv agent\.venv
agent\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r agent\requirements.txt
Copy-Item agent\.env.example agent\.env
```

Edite `agent\.env` antes de executar o cliente.

## Configuração

Configuração mínima:

```dotenv
SERVER_URL=https://casa.exemplo.local
WEBSOCKET_URL=wss://casa.exemplo.local/ws/agents
AGENT_TOKEN=um-token-aleatorio-longo-e-exclusivo
```

Variáveis importantes:

| Variável | Finalidade |
|---|---|
| `SERVER_URL` | URL HTTP(S) do servidor central |
| `WEBSOCKET_URL` | Endpoint WebSocket dos agentes |
| `AGENT_TOKEN` | Token secreto compartilhado com o servidor |
| `AGENT_DATA_DIR` | UUID, configuração do serviço e logs |
| `HEARTBEAT_INTERVAL_SECONDS` | Intervalo da telemetria |
| `VERIFY_TLS` | Validação do certificado HTTPS/WSS |
| `ALLOWED_PROGRAMS_JSON` | Apelidos e caminhos exatos de executáveis |
| `ALLOWED_PROCESSES` | Nomes de processos que podem ser encerrados |
| `ALLOWED_URL_HOSTS` | Hosts que podem ser abertos; vazio permite qualquer host HTTP(S) |

Em produção, use HTTPS/WSS, um token exclusivo por agente e uma lista explícita em `ALLOWED_URL_HOSTS`.

O UUID fica em:

```text
C:\ProgramData\SmartHomeAgent\agent_id
```

Os logs ficam em:

```text
C:\ProgramData\SmartHomeAgent\logs\agent.log
```

## Execução manual

Com o ambiente virtual ativado:

```powershell
python -m agent.main
```

Use `Ctrl+C` para encerrar.

## Instalação como serviço

Abra o PowerShell como Administrador, ative o ambiente virtual e execute:

```powershell
python -m agent.installer install --config agent\.env
```

O instalador:

1. copia o `.env` para `C:\ProgramData\SmartHomeAgent`;
2. restringe o arquivo ao SYSTEM e aos administradores locais;
3. instala `SmartHomeWindowsAgent`;
4. configura inicialização automática;
5. inicia o serviço.

Para remover:

```powershell
python -m agent.installer remove
```

Comandos manuais do serviço:

```powershell
python agent\service.py start
python agent\service.py stop
python agent\service.py restart
python agent\service.py debug
```

Serviços Windows executam na Sessão 0. Para `open_program` e `open_url`, o agente tenta criar o processo na sessão interativa ativa. É necessário haver um usuário conectado. Políticas corporativas podem bloquear essa operação; a falha será registrada no log.

## Protocolo esperado no servidor

O servidor central deve implementar:

### Registro HTTP

```http
POST /api/agents/register
Authorization: Bearer <AGENT_TOKEN>
X-Agent-ID: <UUID>
Content-Type: application/json
```

Payload resumido:

```json
{
  "agent_id": "uuid",
  "hostname": "DESKTOP-SALA",
  "ip_address": "192.168.1.20",
  "os": "Windows",
  "os_version": "...",
  "architecture": "AMD64",
  "agent_version": "1.0.0"
}
```

O endpoint HTTP é opcional para o funcionamento do cliente. Um `404` é registrado e o agente segue tentando o WebSocket.

### WebSocket

```text
GET /ws/agents
Authorization: Bearer <AGENT_TOKEN>
X-Agent-ID: <UUID>
```

Ao conectar, o agente envia:

```json
{
  "type": "hello",
  "payload": {
    "agent_id": "uuid",
    "hostname": "DESKTOP-SALA",
    "capabilities": ["shutdown", "reboot", "lock_screen"],
    "protocol_version": 1
  }
}
```

Heartbeat:

```json
{
  "type": "heartbeat",
  "payload": {
    "agent_id": "uuid",
    "status": "online",
    "cpu_percent": 12.5,
    "ram_percent": 48.1,
    "uptime_seconds": 86400
  }
}
```

Comando enviado pelo servidor:

```json
{
  "type": "command",
  "request_id": "req-123",
  "command": "open_program",
  "params": {
    "program": "notepad"
  }
}
```

Resposta:

```json
{
  "type": "command_result",
  "request_id": "req-123",
  "command": "open_program",
  "success": true,
  "data": {
    "message": "Programa 'notepad' aberto"
  }
}
```

O servidor deve rejeitar tokens inválidos, associar cada conexão ao UUID autenticado e nunca reutilizar `request_id`.

## Segurança

- O servidor nunca fornece caminhos de executáveis.
- `open_program` aceita somente uma chave de `ALLOWED_PROGRAMS_JSON`.
- `close_program` aceita somente nomes de `ALLOWED_PROCESSES`.
- `open_url` aceita somente HTTP(S), sem credenciais e, opcionalmente, apenas hosts cadastrados.
- Mensagens WebSocket maiores que 1 MiB são descartadas.
- No máximo dois comandos são processados simultaneamente.
- Erros enviados ao servidor são limitados; detalhes completos ficam no log local.
- Não há endpoint HTTP local por padrão, reduzindo a superfície de ataque.

## Estrutura

```text
agent/
├── main.py
├── websocket_client.py
├── heartbeat.py
├── commands.py
├── system_info.py
├── config.py
├── logger.py
├── installer.py
├── service.py
├── .env.example
├── requirements.txt
└── README.md
```

## Extensões futuras

A estrutura de capacidades e resultados permite adicionar, após uma revisão de segurança:

- screenshots;
- GPU e temperatura;
- Wake-on-LAN;
- áudio;
- notificações;
- transferência de arquivos;
- controle remoto.
