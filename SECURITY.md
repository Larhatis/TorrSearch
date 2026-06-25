# Politique de sécurité

## Signaler une vulnérabilité

Si tu découvres une faille de sécurité, **ne l'ouvre pas en issue publique**.

Utilise plutôt l'onglet **Security → Report a vulnerability** du dépôt GitHub
(advisory privé), ou contacte le mainteneur en privé. Merci d'inclure :

- une description de la faille et de son impact ;
- les étapes pour la reproduire ;
- la version / le commit concerné.

Un correctif sera préparé en privé puis publié avec mention (si tu le souhaites).

## Bonnes pratiques de déploiement

TorrSearch est conçu pour l'auto-hébergement. Pour une exposition sûre :

- **Active l'authentification** (`TORSEARCH_USERNAME` / `TORSEARCH_PASSWORD`) avec un
  mot de passe fort.
- Place l'app **derrière un reverse proxy HTTPS** et mets `TORSEARCH_HTTPS=1`.
- Garde `data/` (qui contient `users.json`, `settings.json`, les passkeys des trackers)
  privé et sauvegardé.

Voir la section *Sécurité & exposition* du `README`.
