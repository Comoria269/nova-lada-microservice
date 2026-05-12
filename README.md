# NOVA-Lada — Microservice post-purchase

Microservice FastAPI qui automatise les emails transactionnels de Lada Vanilia : reçoit les webhooks Stripe, déclenche les emails Brevo (Confirmation, Expédition, Demande d'avis).

**Domaine de prod** : `https://nova.ladavanilia.com`
**Stack** : Python 3.11 · FastAPI · Stripe SDK · Brevo SDK · Docker · Coolify

---

## Architecture

```
Stripe (paiement OK)
    │
    ▼ webhook signé
https://nova.ladavanilia.com/webhook/stripe
    │
    ▼ API Brevo
Email Template 1 (Confirmation) → client
```

Templates 2 (Expédition) et 3 (Avis) sont déclenchés manuellement par l'admin via les endpoints `/admin/send-shipping` et `/admin/send-review`.

---

## Endpoints

| Méthode | URL | Auth | Rôle |
|---|---|---|---|
| GET  | `/health` | Aucune | Healthcheck Coolify |
| POST | `/webhook/stripe` | Signature Stripe | Reçoit `checkout.session.completed` → envoie Template 1 |
| POST | `/admin/send-shipping` | Header `X-Admin-Token` | Envoie Template 2 |
| POST | `/admin/send-review` | Header `X-Admin-Token` | Envoie Template 3 |
| GET  | `/admin/ping` | Header `X-Admin-Token` | Test du token admin |

---

## Variables d'environnement

Voir [`.env.example`](.env.example). Toutes obligatoires sauf indication.

| Variable | Description |
|---|---|
| `STRIPE_API_KEY` | Restricted key Stripe (lecture sur Payment Intents + Checkout Sessions + Customers) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret du webhook configuré sur Stripe |
| `BREVO_API_KEY` | API key Brevo (xkeysib-…) |
| `BREVO_TEMPLATE_CONFIRMATION_ID` | ID du Template 1 (par défaut: 2) |
| `BREVO_TEMPLATE_EXPEDITION_ID` | ID du Template 2 (par défaut: 3) |
| `BREVO_TEMPLATE_AVIS_ID` | ID du Template 3 (par défaut: 4) |
| `ADMIN_API_TOKEN` | Token pour appeler les endpoints `/admin/*`. Générer avec `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ENVIRONMENT` | `production` (cache la doc /docs) ou `dev` |
| `LOG_LEVEL` | `INFO`, `DEBUG`, `WARNING` |
| `DEFAULT_SHIPPING_DAYS` | Délai de livraison estimé en jours ouvrés (4 par défaut) |

---

## Déploiement Coolify (pas-à-pas)

### 1. Préparer le repo GitHub

```bash
cd ~/Desktop
mv ladavanilia-site/nova-lada-microservice ./nova-lada-microservice
cd nova-lada-microservice
git init
git add .
git commit -m "feat: initial NOVA-Lada microservice"
```

Sur GitHub → **New repository** → nom : `nova-lada-microservice` → **Private** → Create. Puis :

```bash
git remote add origin git@github.com:Comoria269/nova-lada-microservice.git
git branch -M main
git push -u origin main
```

### 2. Générer le token admin

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copie le résultat et sauvegarde-le dans **Bitwarden** dans le folder ORION V5.

### 3. Créer la restricted key Stripe

1. https://dashboard.stripe.com → **Développeurs** → **Clés API** → **Créer une clé restreinte**
2. Nom : `nova-lada-microservice`
3. Permissions (Read uniquement) :
   - Checkout Sessions : **Read**
   - Payment Intents : **Read**
   - Customers : **Read**
4. Tout le reste : **None**
5. Copie la clé `rk_live_…`

### 4. Déployer sur Coolify

1. https://coolify.ladavanilia.com → **+ New Resource** → **Public/Private Repository**
2. Sélectionne `Comoria269/nova-lada-microservice` (branch `main`)
3. **Build Pack** : Dockerfile
4. **Domain** : `nova.ladavanilia.com` (HTTPS Let's Encrypt automatique)
5. **Port** : 8000
6. **Environment Variables** : colle toutes les vars depuis `.env.example` avec les vraies valeurs :
   - `STRIPE_API_KEY` = `rk_live_…` (étape 3)
   - `STRIPE_WEBHOOK_SECRET` = `whsec_…` (étape 5)
   - `BREVO_API_KEY` = `xkeysib-…` (depuis Bitwarden)
   - `BREVO_TEMPLATE_CONFIRMATION_ID` = `2`
   - `BREVO_TEMPLATE_EXPEDITION_ID` = `3`
   - `BREVO_TEMPLATE_AVIS_ID` = `4`
   - `ADMIN_API_TOKEN` = token étape 2
   - `ENVIRONMENT` = `production`
   - `LOG_LEVEL` = `INFO`
   - `DEFAULT_SHIPPING_DAYS` = `4`
7. **Healthcheck path** : `/health`
8. **Deploy**

### 5. Configurer le webhook Stripe

1. https://dashboard.stripe.com → **Développeurs** → **Webhooks** → **Ajouter un endpoint**
2. URL : `https://nova.ladavanilia.com/webhook/stripe`
3. Description : `NOVA-Lada — emails post-purchase`
4. Events à écouter : **`checkout.session.completed`**
5. Récupère le **Signing secret** (`whsec_…`)
6. Retourne dans Coolify → env vars → mets à jour `STRIPE_WEBHOOK_SECRET` → **Redeploy**
7. De retour sur Stripe → click **"Envoyer un événement de test"** → choisis `checkout.session.completed` → Send
8. Vérifie : statut **200 OK** dans Stripe + log `confirmation.sent` dans Coolify

---

## Tests

### Healthcheck

```bash
curl https://nova.ladavanilia.com/health
# {"status":"ok","service":"nova-lada","env":"production"}
```

### Test admin token

```bash
curl -H "X-Admin-Token: $ADMIN_API_TOKEN" https://nova.ladavanilia.com/admin/ping
# {"status":"ok"}
```

### Déclencher manuellement Template 2 (Expédition)

```bash
curl -X POST https://nova.ladavanilia.com/admin/send-shipping \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "marie@example.com",
    "prenom": "Marie",
    "commande_id": "ABC12345",
    "numero_suivi": "8L12345678901"
  }'
```

OU à partir d'une session Stripe :

```bash
curl -X POST https://nova.ladavanilia.com/admin/send-shipping \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "cs_live_xxxxx",
    "commande_id": "ABC12345",
    "numero_suivi": "8L12345678901"
  }'
```

### Déclencher manuellement Template 3 (Avis)

```bash
curl -X POST https://nova.ladavanilia.com/admin/send-review \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"marie@example.com","prenom":"Marie"}'
```

---

## Limites connues

- **PayPal non couvert** : le flow PayPal du site capture côté client, sans webhook. Les clients PayPal ne reçoivent **pas** automatiquement l'email de confirmation. Solution future : migrer le tunnel PayPal vers Stripe Checkout ou ajouter un webhook PayPal dans ce service.
- **Idempotence en mémoire** : à un redémarrage du conteneur, le set des event_id traités est vidé. Stripe gère sa propre dedup au niveau de l'envoi, donc impact pratiquement nul. Pour aller plus loin : persister dans Redis.
- **Pas de retry custom** : si Brevo répond 5xx, on renvoie 500 et c'est Stripe qui retry (jusqu'à 3 jours avec backoff exponentiel).

---

## Dev local

```bash
cp .env.example .env
# édite .env avec tes vraies clés (mode test Stripe recommandé)
docker compose up --build
```

Puis dans un autre terminal :

```bash
# Test ngrok pour recevoir les webhooks Stripe en local
ngrok http 8000
# Mets l'URL ngrok dans Stripe webhook (mode test)
```

---

## Sécurité

- Webhook Stripe : signature **systématiquement** validée.
- Endpoints admin : token comparé en temps constant (`secrets.compare_digest`).
- Conteneur Docker : user non-root.
- Aucune donnée client persistée (stateless).
- Pas de secrets en clair dans le code (uniquement via env vars Coolify).
