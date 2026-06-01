# 🚀 Integração Roku - Guia Rápido

Integre sua TV Roku em 3 passos simples! Informe apenas o IP e controle completamente.

## 🔍 Passo 1: Encontre o IP da sua TV Roku

**Na TV:**
1. Pressione HOME no controle remoto
2. Settings → System → About → IP Address

**No Router:**
- Acesse seu painel do roteador e procure pelo Roku na lista de dispositivos

## 📝 Passo 2: Descubra o Roku

```bash
curl -X POST http://localhost:8000/roku/discover \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}'
```

Substitua `192.168.1.100` pelo IP da sua TV.

Se encontrar, verá:
```json
{
  "success": true,
  "online": true,
  "message": "Roku encontrado!"
}
```

## ✅ Passo 3: Cadastre no Sistema

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
  "message": "Roku 'Roku Sala' cadastrado com sucesso!"
}
```

## 🎮 Controlar seu Roku

Agora pode controlar usando o `device_id` retornado (ex: `1`):

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

### Abrir Netflix
```bash
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "launch_app",
    "params": {"app_id": "netflix"}
  }'
```

### Ver Status
```bash
curl -X GET "http://localhost:8000/roku/devices/1/status"
```

## 📱 Usar Script de Teste (Python)

Se tiver Python, use o script de teste:

```bash
# Descobrir
python test_roku.py discover 192.168.1.100

# Registrar
python test_roku.py register 192.168.1.100 "Roku Sala"

# Ligar
python test_roku.py command 1 turn_on

# Desligar
python test_roku.py command 1 turn_off

# Abrir Netflix
python test_roku.py command 1 launch_app netflix

# Ver Status
python test_roku.py status 1
```

## 📚 Apps Suportados

Abra qualquer um destes apps:
- `netflix` - Netflix
- `youtube` - YouTube
- `prime` - Amazon Prime Video
- `hulu` - Hulu
- `disney` - Disney+
- `hbo` - HBO Max

```bash
# Exemplo: Abrir YouTube
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "launch_app",
    "params": {"app_id": "youtube"}
  }'
```

## 🎯 Comandos de Controle Remoto

```bash
# Enviar comando (navegação)
curl -X POST "http://localhost:8000/roku/devices/1/control?token=smart-home-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "send_command",
    "params": {"command": "play"}
  }'
```

Comandos: `home`, `back`, `left`, `right`, `up`, `down`, `select`, `play`, `pause`, `rewind`, `forward`

## 🐛 Problemas?

### "Roku não encontrado"
- ✓ Verifique o IP (deve estar na mesma rede)
- ✓ TV deve estar ligada ou em standby
- ✓ Teste: `ping 192.168.1.100`

### Comandos não funcionam
- ✓ Certifique-se que registrou com `/roku/register`
- ✓ Use o `device_id` correto
- ✓ Verifique o token: `smart-home-token-123`

---

## 📖 Documentação Completa

Veja [ROKU.md](ROKU.md) para documentação detalhada com mais exemplos.

## 🌐 Via Dashboard

Após registrar, seu Roku aparece na dashboard em:
- **http://localhost:8000/**
- Com botões para ligar/desligar
- Status em tempo real
- Integração com automações

---

**Dúvidas?** Consulte:
- [ROKU.md](ROKU.md) - Documentação completa
- [README.md](README.md) - Guia geral do sistema
- `/api/info` - Informações dos endpoints da API

**Sugestão:** Combine com automações para criar cenários (ex: desligar TV ao sair de casa)
