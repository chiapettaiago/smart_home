# Smart Home Server - Mini Home Assistant

Um sistema de automação residencial construído em Python com Flask, dashboard web moderna e arquitetura pronta para integrações futuras com Tuya, Roku, Android e agentes de PC.

![Status](https://img.shields.io/badge/status-beta-yellow)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![Flask](https://img.shields.io/badge/flask-3.0+-green)

## 🎯 Características

### ✅ Implementado
- **Dashboard Web Moderna**: Interface responsiva e intuitiva com sidebar, cards de status e controles
- **API RESTful Completa**: Endpoints Flask para dispositivos, presença, energia, automações e ações
- **Atualização Automática**: Dashboard atualizado periodicamente
- **Banco de Dados SQLite**: Modelagem completa com SQLAlchemy para todas as entidades
- **Cadastro de Dispositivos**: CRUD funcional com suporte a múltiplos tipos (Tuya, Roku, Android, PC Windows/Linux, Sensores)
- **Sistema de Ações Mockado**: Arquitetura pronta para expansão com whitelist de ações seguras
- **Consumo de Energia**: Registro e visualização de consumo por dispositivo
- **Presença de Usuários**: Rastreamento de quem está em casa
- **Automações**: Estrutura para criar regras (implementação básica)
- **Segurança**: Autenticação por token, whitelist de ações, validação de entrada
- **Integração com Roku TV**: Controle completo via IP (ligar, desligar, abrir apps, navegar)
- **Integração Pronta**: Estrutura em `/integrations/` para Tuya, Android e PC Agents

### 🚀 Próximas Etapas
- [ ] Integração real com Tuya IoT Platform
- [ ] Integração com Roku TV (controle via IP)
- [ ] Integração com Android (via agente)
- [ ] Integração com PC Windows/Linux (via agente)
- [ ] Scheduler de automações
- [ ] Histórico de eventos avançado
- [ ] Sistema de notificações (email, push)
- [ ] Gráficos de consumo e analytics
- [ ] Autenticação de usuários
- [ ] Backup e restauração de dados

## 📋 Requisitos

- Python 3.9+
- pip
- Conexão à rede (para comunicação com dispositivos)

## 🚀 Instalação

### 1. Clonar ou copiar o repositório

```bash
cd smart-home-server
```

### 2. Criar ambiente virtual

```bash
# Linux/Mac
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar .env com suas configurações
nano .env
```

Configurações importantes:
```env
ENVIRONMENT=development              # Use production em produção
DEBUG=False
HOST=0.0.0.0                         # Interface de escuta
PORT=8000                            # Porta do servidor
SECRET_KEY=gere-um-segredo-aleatorio # Obrigatório em produção
API_TOKEN=gere-um-token-aleatorio    # Token Bearer para clientes da API
AUTH_USERNAME=admin                 # Login da interface web
AUTH_PASSWORD_HASH=scrypt:...       # Hash gerado pelo Werkzeug
SESSION_COOKIE_SECURE=False         # Use True com HTTPS em produção

# Banco de dados MySQL
DATABASE_URL=mysql+pymysql://smart_home:senha@127.0.0.1:3306/smart_home?charset=utf8mb4

# Integrações (deixe em branco se não usar)
TUYA_API_KEY=
TUYA_API_SECRET=
```

## ▶️ Como Rodar

### Método 1: Script direto

```bash
python run.py
```

### Método 2: Flask direto

```bash
flask --app app.main run --host 0.0.0.0 --port 8000 --debug
```

### Método 3: Com gunicorn (produção)

```bash
gunicorn -w 4 app.main:app
```

O servidor iniciará em:
- 📊 Dashboard: `http://localhost:8000/`
- 📚 API: `http://localhost:8000/api/info`

## 📱 Interface Web

A dashboard oferece:

### Visão Geral
- Cards com status de dispositivos online/offline
- Consumo elétrico atual
- Presença de usuários
- Automações ativas

### Dispositivos
- Lista de todos os dispositivos cadastrados
- Cards com status em tempo real
- Botões de ação (ligar/desligar)
- Filtro por cômodo

### Energia
- Consumo total nas últimas 24h
- Consumo por dispositivo
- Gráfico visual (em desenvolvimento)

### Automações
- Lista de automações criadas
- Status ativo/inativo
- Histórico de execução

### Presença
- Status de cada usuário
- Marcar como em casa/fora de casa

## 🔌 API REST - Endpoints Principais

Clientes externos devem enviar `Authorization: Bearer seu-token`. O painel web usa
sessão protegida e token CSRF automaticamente.

### Dispositivos

```bash
# Listar dispositivos
GET /devices

# Criar dispositivo
POST /devices
  {
    "name": "Ar Condicionado",
    "type": "tuya",
    "room": "sala",
    "ip": "192.168.1.100",
    "token": "token-do-dispositivo"
  }

# Obter dispositivo específico
GET /devices/{id}

# Atualizar dispositivo
PUT /devices/{id}

# Deletar dispositivo
DELETE /devices/{id}

# Executar ação
POST /devices/{id}/action
  {
    "action": "turn_on",
    "params": {}
  }

# Ações disponíveis:
# - turn_on (ligar)
# - turn_off (desligar)
# - restart (reiniciar)
# - lock (bloquear)
# - unlock (desbloquear)
# - get_status (obter status)
# - open_app (abrir app) - requer 'app_name' em params
# - close_app (fechar app) - requer 'app_name' em params
```

### Presença

```bash
# Marcar usuário em casa
POST /presence/{user}/home

# Marcar usuário fora de casa
POST /presence/{user}/away

# Obter presença de um usuário
GET /presence/{user}

# Obter presença de todos
GET /presence

# Forçar atualização pelo Vivo Box configurado
POST /presence/router/refresh
```

Para detectar automaticamente se um celular está conectado ao Vivo Box Askey,
configure somente no `.env` local:

```env
VIVO_ROUTER_URL=http://192.168.15.1
VIVO_ROUTER_USERNAME=
VIVO_ROUTER_PASSWORD=
PRESENCE_PHONE_MAC=AA:BB:CC:DD:EE:FF
PRESENCE_USER=Iago
PRESENCE_ROUTER_INTERVAL_SECONDS=30
PRESENCE_ROUTER_AWAY_MISSES=3
```

Não preencha credenciais reais no `.env.example`. O endereço MAC deve ser o MAC
privado usado pelo celular especificamente na rede Wi-Fi residencial.

Teste a detecção antes de iniciar o servidor:

```bash
venv/bin/python scripts/check_vivo_router_presence.py
```

### Energia

```bash
# Adicionar leitura de energia
POST /energy/readings
  {
    "device_id": 1,
    "watts": 1500,
    "voltage": 220,
    "current": 6.8,
    "kwh": 0.5
  }

# Obter leituras de um dispositivo
GET /energy/readings/{device_id}

# Consumo total (24h)
GET /energy/consumption/total

# Consumo por dispositivo
GET /energy/consumption/by-device

# Última leitura de um dispositivo
GET /energy/last-reading/{device_id}
```

### Automações

```bash
# Listar automações
GET /automations

# Criar automação
POST /automations
  {
    "name": "Ligar luzes ao entardecer",
    "trigger": "time",
    "condition": {"time": "18:00"},
    "actions": [
      {"device_id": 1, "action": "turn_on"}
    ],
    "active": true
  }

# Obter automação específica
GET /automations/{id}

# Atualizar automação
PUT /automations/{id}

# Deletar automação
DELETE /automations/{id}

# Automações ativas
GET /automations/active/list

# Logs de execução
GET /automations/{id}/logs
```

### Dashboard

```bash
# Dados consolidados
GET /api/dashboard/data
```

## 🔄 Atualização do Dashboard

O dashboard consulta os dados consolidados em `GET /api/dashboard/data` a cada cinco segundos.

## 🔗 Integrações

### Roku TV ✅ Implementado
Controle completo de TV Roku informando apenas o IP.

**Começar:**
```bash
curl -X POST http://localhost:8000/roku/discover \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}'
```

Ver [ROKU.md](ROKU.md) para documentação completa.

### Tuya IoT 🚧 Em Desenvolvimento
Integração com plataforma Tuya para controlar dispositivos inteligentes.

### Android 🚧 Em Desenvolvimento
Controle de dispositivos Android via agente.

### PC Windows/Linux 🚧 Em Desenvolvimento
Agente para controlar computadores via rede.

---

## 🎮 Exemplos de Uso

### Controlando Roku

```bash
# Descobrir Roku
curl -X POST http://localhost:8000/roku/discover \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}'

# Cadastrar Roku
curl -X POST "http://localhost:8000/roku/register" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100", "name": "Roku Sala"}'

# Ligar TV
curl -X POST "http://localhost:8000/roku/devices/1/control" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "turn_on"}'

# Abrir Netflix
curl -X POST "http://localhost:8000/roku/devices/1/control" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "launch_app", "params": {"app_id": "netflix"}}'

# Obter status
curl -X GET "http://localhost:8000/roku/devices/1/status" \
  -H "Authorization: Bearer $API_TOKEN"
```

---

```
smart-home-server/
├── app/
│   ├── main.py              # Aplicação Flask principal
│   ├── config.py            # Configurações e constantes
│   ├── database.py          # Setup do SQLAlchemy
│   ├── models.py            # Modelos SQLAlchemy
│   ├── routers/
│   │   ├── devices.py       # Endpoints de dispositivos
│   │   ├── presence.py      # Endpoints de presença
│   │   ├── energy.py        # Endpoints de energia
│   │   ├── automations.py   # Endpoints de automações
│   │   └── dashboard.py     # Endpoint de dados da dashboard
│   ├── services/
│   │   ├── device_service.py     # Lógica de dispositivos
│   │   ├── action_service.py     # Lógica de ações
│   │   ├── presence_service.py   # Lógica de presença
│   │   ├── energy_service.py     # Lógica de energia
│   │   └── automation_service.py # Lógica de automações
│   ├── integrations/
│   │   ├── tuya.py          # Integração Tuya (placeholder)
│   │   ├── roku.py          # Integração Roku (placeholder)
│   │   ├── android.py       # Integração Android (placeholder)
│   │   └── pc_agent.py      # Integração PC Agent (placeholder)
│   ├── templates/
│   │   └── dashboard.html   # Template HTML da dashboard
│   └── static/
│       ├── css/
│       │   └── dashboard.css # Estilos da dashboard
│       └── js/
│           └── dashboard.js  # Lógica da dashboard
├── run.py                   # Script para iniciar servidor
├── requirements.txt         # Dependências Python
├── .env.example            # Exemplo de variáveis de ambiente
├── .gitignore              # Arquivos para ignorar no git
└── README.md               # Este arquivo
```

## 🔐 Segurança

### Medidas Implementadas

1. **Sessão protegida**: Cookies `HttpOnly`, `SameSite=Strict`, expiração e CSRF
2. **Senha com hash**: Produção exige `AUTH_PASSWORD_HASH`
3. **Proteção contra força bruta**: Tentativas repetidas bloqueiam temporariamente o login
4. **Token Bearer**: Clientes externos usam `Authorization`, sem segredo na URL
5. **Headers defensivos**: CSP, HSTS sob HTTPS, anti-frame e `no-referrer`
6. **Whitelist de ações**: Apenas ações pré-aprovadas podem ser executadas

### Recomendações para Produção

1. **Defina `ENVIRONMENT=production`, `SECRET_KEY`, `API_TOKEN` e `AUTH_PASSWORD_HASH`**
2. **Use HTTPS** com certificado válido e `SESSION_COOKIE_SECURE=True`
3. **Use senhas MySQL fortes** e mantenha o banco acessível somente na rede necessária
4. **Ative logs e monitoramento**
5. **Configure firewall** para restringir acesso
6. **Use reverse proxy** (nginx) em produção

Troque a senha local sem expô-la no histórico do terminal:

```bash
venv/bin/python scripts/set_password.py
```

## 🔧 Desenvolvimento

### Adicionar Novo Endpoint

1. Criar função no router apropriado em `app/routers/`
2. Abrir uma sessão com `db = get_db()` e fechá-la em `finally`
3. Retornar JSON com `jsonify`

Exemplo:
```python
@blueprint.get("/devices")
def get_devices():
    db = get_db()
    try:
        return jsonify(serialize(DeviceService.get_devices(db)))
    finally:
        db.close()
```

### Adicionar Novo Tipo de Dispositivo

1. Adicionar em `DEVICE_TYPES` em `config.py`
2. Criar integração em `app/integrations/novo_tipo.py`
3. Adicionar ícone em `getDeviceIcon()` em `static/js/dashboard.js`

### Implementar Integração Real

Usar arquivo placeholder em `app/integrations/`:

```python
# app/integrations/novo.py
class NovaIntegration:
    def __init__(self, ...):
        pass
    
    def turn_on(self):
        # Implementar chamada real
        pass
    
    def get_status(self):
        # Implementar chamada real
        pass
```

## 🚨 Troubleshooting

### Erro: "Port already in use"
```bash
# Mudar porta em .env
PORT=8001
```

### Migrar SQLite para MySQL

Instale as dependências e corrija o proprietário dos arquivos legados:

```bash
venv/bin/pip install -r requirements.txt
sudo chown $(id -u):$(id -g) .env smart_home.db
sudo chmod 600 .env smart_home.db
```

Para iniciar um MySQL local com Docker Compose, defina senhas fortes e suba o serviço:

```bash
export MYSQL_PASSWORD='troque-esta-senha'
export MYSQL_ROOT_PASSWORD='troque-esta-senha-root'
docker compose -f compose.mysql.yml up -d
```

Copie e valide os dados antes de alterar `DATABASE_URL` no `.env`:

```bash
export MYSQL_DATABASE_URL='mysql+pymysql://smart_home:senha@127.0.0.1:3306/smart_home?charset=utf8mb4'
venv/bin/python scripts/migrate_sqlite_to_mysql.py
```

Depois da validação, configure no `.env`:

```env
DATABASE_URL=mysql+pymysql://smart_home:senha@127.0.0.1:3306/smart_home?charset=utf8mb4
```

### Erro legado: "Database is locked"
```bash
# O SQLite é mantido somente como backup após a migração.
# Não apague o arquivo antes de validar o MySQL.
```

## 📚 Documentação Adicional

- Informações da API: `http://localhost:8000/api/info`

## 🤝 Contribuindo

Para adicionar features ou corrigir bugs:

1. Criar branch: `git checkout -b feature/minha-feature`
2. Fazer commits: `git commit -m "Adiciona minha feature"`
3. Push: `git push origin feature/minha-feature`

## 📄 Licença

MIT License - veja LICENSE para detalhes

## 🆘 Suporte

Para dúvidas ou problemas:
- Abrir issue no repositório
- Verificar informações da API em `/api/info`
- Consultar exemplos em `/examples`

---

**Desenvolvido com ❤️ para domótica em Python**

Próximas integrações em progresso: Tuya, Roku, Android, PC Agents
