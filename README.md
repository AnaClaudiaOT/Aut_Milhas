# Monitor de promocoes de milhas no Telegram

Este projeto monitora novas promocoes de transferencia bonificada entre:

- Esfera -> Smiles
- Itau -> Smiles
- Esfera -> Azul
- Itau -> Azul

Quando encontra uma promocao nova nas fontes monitoradas, envia um alerta para o Telegram.

## Como funciona

O script consulta paginas de promocoes e milhas, filtra titulos relacionados aos pares desejados e guarda as URLs ja alertadas em `data/seen_promos.json`.

No GitHub, o workflow roda todos os dias em dois horarios:

- 09:07 no horario de Sao Paulo
- 21:07 no horario de Sao Paulo

Os minutos `07` foram escolhidos para evitar o comeco exato da hora, quando o GitHub Actions pode sofrer mais atraso em execucoes agendadas.

## Fontes monitoradas

- `https://www.melhoresdestinos.com.br/milhas`
- `https://passageirodeprimeira.com/categorias/promocoes/`

## O que voce precisa criar

### 1. Um bot no Telegram

1. Fale com o `@BotFather` no Telegram.
2. Use o comando `/newbot`.
3. Defina nome e username do bot.
4. Guarde o token gerado.

### 2. Seu chat ID no Telegram

Voce pode descobrir de algumas formas. A mais simples costuma ser:

1. Enviar uma mensagem para o seu bot.
2. Abrir no navegador:

```text
https://api.telegram.org/botSEU_TOKEN/getUpdates
```

3. Procurar o campo `chat` e copiar o `id`.

## Devo criar um repositorio no GitHub?

Sim. Esse e o melhor caminho se voce quer que a automacao rode sem depender do seu computador ligado.

Fluxo recomendado:

1. Criar um repositorio no seu GitHub.
2. Adicionar este projeto ao repositorio.
3. Configurar os secrets do GitHub.
4. Ativar o workflow.

## Secrets do GitHub

No repositorio, crie estes secrets em `Settings -> Secrets and variables -> Actions`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Como subir o projeto

Depois de criar o repositorio no GitHub, conecte este repo local ao remoto:

```bash
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git branch -M main
git add .
git commit -m "feat: add miles promotion telegram monitor"
git push -u origin main
```

## Como testar

Voce pode rodar manualmente pelo GitHub em `Actions -> Promo Monitor -> Run workflow`.

Se houver uma promocao nova ainda nao registrada em `data/seen_promos.json`, o bot envia a mensagem no Telegram.

## Observacoes

- O monitor envia alerta apenas para URLs novas.
- Se voce quiser receber novamente uma promocao ja detectada, remova a URL correspondente de `data/seen_promos.json`.
- Como o monitor depende da estrutura das paginas, pode ser necessario ajustar os filtros no futuro se os sites mudarem.
- Este projeto prioriza simplicidade e baixo custo operacional.
