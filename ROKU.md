# Guia de Integração Roku TV

Este guia explica como integrar e controlar sua TV Roku usando o Smart Home Server.

## 🚀 Começar Rapidamente

### 1. Descobrir Roku pelo IP

```bash
curl -X POST http://localhost:8000/roku/discover \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}'
```

Resposta se encontrado:
```json
{
  "success": true,
  "ip": "192.168.1.100",
  "online": true,
  "powered_on": false,
  "message": "Roku encontrado!",
  "next_step": "Use POST /roku/register para cadastrar este Roku como dispositivo"
}
```

### 2. Cadastrar Roku no Sistema

```bash
curl -X POST "http://localhost:8000/roku/register?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "192.168.1.100",
    "name": "Roku Sala"
  }'
```

Resposta:
```json
{
  "success": true,
  "device_id": 1,
  "name": "Roku Sala",
  "ip": "192.168.1.100",
  "message": "Roku 'Roku Sala' cadastrado com sucesso!",
  "next_step": "Use POST /devices/1/action para controlar"
}
```

## 🎮 Controlando o Roku

### Ligar TV

```bash
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{"command": "turn_on"}'
```

### Desligar TV

```bash
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{"command": "turn_off"}'
```

### Abrir Aplicativo

Abrir Netflix:
```bash
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "launch_app",
    "params": {"app_id": "netflix"}
  }'
```

Apps suportados:
- `netflix` - Netflix
- `youtube` - YouTube
- `prime` - Amazon Prime Video
- `hulu` - Hulu
- `disney` - Disney+
- `hbo` - HBO Max

### Enviar Comando de Controle Remoto

```bash
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "send_command",
    "params": {"command": "play"}
  }'
```

Comandos disponíveis:
- `home` - Home
- `back` - Voltar
- `left` - Esquerda
- `right` - Direita
- `up` - Acima
- `down` - Abaixo
- `select` - Selecionar
- `play` - Play
- `pause` - Pause
- `rewind` - Retroceder
- `forward` - Avançar

### Fechar Aplicativo (Voltar para Home)

```bash
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{"command": "close_app"}'
```

### Obter Status

```bash
curl -X GET "http://localhost:8000/roku/devices/1/status" \
  -H "Content-Type: application/json"
```

Resposta:
```json
{
  "device_id": 1,
  "device_name": "Roku Sala",
  "ip": "192.168.1.100",
  "online": true,
  "powered_on": false,
  "status": {
    "success": true,
    "online": true,
    "powered_on": false,
    "message": "Status obtido com sucesso"
  }
}
```

### Obter Lista de Apps

```bash
curl -X GET "http://localhost:8000/roku/devices/1/apps"
```

Resposta:
```json
{
  "device_id": 1,
  "device_name": "Roku Sala",
  "apps": {
    "Netflix": "12",
    "YouTube": "837",
    "Amazon Prime": "13",
    "Hulu": "3",
    "Disney+": "549",
    "HBO Max": "61322"
  },
  "success": true
}
```

## 📱 Via Dashboard

Na dashboard web, você pode:

1. **Ligar/Desligar**: Clique nos botões Ligar/Desligar do card do Roku
2. **Ver Status**: O status online/offline é atualizado em tempo real
3. **Enviar Comandos**: Via interface do dispositivo

## 🔍 Encontrar o IP do Roku

### Método 1: Na TV
1. Pressione HOME no controle remoto
2. Vá para Settings (Configurações)
3. Vá para System (Sistema)
4. Vá para About (Sobre)
5. Procure por "IP Address"

### Método 2: Router
Acesse o painel do seu roteador e procure pelo dispositivo Roku na lista de dispositivos conectados.

### Método 3: Usar Roku App
Use a aplicação móvel oficial do Roku para encontrar o IP na seção de configurações.

## 🔄 Atualização do Dashboard

O dashboard consulta periodicamente o estado dos dispositivos cadastrados.

## ⚙️ Integração com Automações

Você pode criar automações que controlem o Roku:

```bash
curl -X POST "http://localhost:8000/automations?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Desligar TV ao dormir",
    "trigger": "time",
    "condition": {"time": "22:00"},
    "actions": [
      {
        "device_id": 1,
        "command": "turn_off"
      }
    ],
    "active": true
  }'
```

## 🐛 Troubleshooting

### "Roku não encontrado neste IP"
- ✓ Verifique se o IP está correto
- ✓ Certifique-se que a TV está na mesma rede
- ✓ Verifique se o Roku está ligado
- ✓ Teste ping: `ping 192.168.1.100`

### "Conexão recusada"
- ✓ O Roku pode estar em standby (modo sleep)
- ✓ Verifique se a porta 8060 está acessível
- ✓ Reinicie o Roku

### Comandos não funcionam
- ✓ Verifique o token de autenticação
- ✓ Teste primeiro com `/roku/discover` para confirmar conexão
- ✓ Verifique os logs do servidor

## 📚 Referências

- [API Roku REST](https://developer.roku.com/en-GB/docs/developer-program/debugging/external-control-api.md)
- [Roku Developer Portal](https://developer.roku.com/)

## 💡 Dicas

1. **Performance**: A descoberta do Roku leva alguns segundos. Isto é normal.
2. **Bateria**: Se usar em Android/Mobile, isto consome bateria do dispositivo.
3. **Múltiplos Rokus**: Você pode cadastrar e controlar várias TVs Roku.
4. **Automações**: Combine com outras automações para criar rotinas (ex: desligar TV quando sair de casa).

---

**Próximas Integrações**: Google Chromecast, Fire TV, Smart TVs Samsung
