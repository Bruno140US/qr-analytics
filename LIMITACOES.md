# Limitações do QR Analytics

## Visitantes únicos (aproximação)

A métrica **visitantes únicos** do dashboard **não identifica pessoas**. Ela usa uma combinação aproximada de:

- Endereço IP do visitante
- User-Agent completo do navegador (navegador + versão + sistema operacional + dispositivo)

Esses dois valores são combinados e passam por um hash SHA-256. Duas visitas com o **mesmo hash** contam como **um** visitante único.

### Por que isso é aproximado

| Situação | Efeito na contagem |
|---|---|
| Mesma pessoa, mesmo celular, mesma rede Wi-Fi | Contada **uma vez** ✅ |
| Mesma pessoa trocando Wi-Fi → 4G | Contada **duas vezes** ❌ |
| Duas pessoas na mesma rede (empresa/escola com NAT) | Contadas **duas vezes** ✅ (UA geralmente difere) |
| Duas pessoas no mesmo celular (mesmo IP e mesmo UA) | Contadas **uma vez** ❌ |
| Pessoa usando VPN | Contada como se estivesse na VPN ❌ |
| Navegador atualizando (UA muda entre versões) | Contada **duas vezes** ❌ |
| Modo anônimo | Mesmo IP/UA, contada **uma vez** ✅ |

### O que NÃO fazemos

- Não usamos **cookies** de rastreamento
- Não usamos **fingerprinting** agressivo (canvas, fontes, áudio)
- Não coletamos **GPS** (podemos adicionar depois, com consentimento)
- Não cruzamos dados com redes sociais ou outros sites

### Sobre LGPD

- Coletamos **IP** e **User-Agent** para fins de analytics agregado
- Os dados são armazenados **localmente** no SQLite
- Podemos anonimizar o IP antes de armazenar (hash + truncar) em versão futura
- Um aviso de privacidade precisa ser exibido quando o projeto for público

### Como interpretar os números no dashboard

- **Total de scans**: número bruto de vezes que o QR foi acessado
- **Visitantes únicos**: pessoas **aproximadamente** únicas que acessaram
- Se `únicos` estiver muito próximo de `total`: poucos retornos
- Se `únicos` estiver bem abaixo de `total`: mesmo público voltando várias vezes