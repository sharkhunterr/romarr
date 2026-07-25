"""Handlers de backup — un module par type de ressource.

Chaque module :
  1. Importe son modèle ORM cible
  2. Définit une classe qui implémente `ResourceHandler`
  3. Appelle `register(instance)` au top-level pour s'auto-enregistrer

Le registre `romarr.backup.registry._REGISTRY` est peuplé la première
fois que `_ensure_loaded()` est appelé (au premier accès à l'API
`/api/v3/backup/manifest` ou similaire).
"""
