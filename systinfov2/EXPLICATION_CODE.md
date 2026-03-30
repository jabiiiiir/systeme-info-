# Explication complète du code — Voodoo Production Manager

---

## 1. Vue d'ensemble : c'est quoi cette application ?

C'est une application de bureau (fenêtre Windows) construite avec **PyQt6**.
Elle permet à une boulangerie de :
- Gérer ses machines et ses produits (Configuration)
- Consulter les prix de l'électricité en temps réel (ENTSO-E)
- Créer des commandes de production et calculer leur coût énergétique
- Envoyer automatiquement des emails aux opérateurs et au responsable

---

## 2. Structure des fichiers

```
main.py               → point d'entrée, fenêtre principale
config.py             → identifiants (email, token API)
database.py           → toutes les opérations sur la base de données SQLite
api_entsoe.py         → récupère les prix de l'électricité depuis internet
email_sender.py       → envoie des emails via Gmail
tab_configuration.py  → onglet "Configuration" (machines + produits)
tab_prix.py           → onglet "Prix Électricité" (graphique + seuil)
tab_commandes.py      → onglet "Commandes" (créer/supprimer + calculer coûts)
ui/                   → fichiers .ui créés avec Qt Designer (interface visuelle)
```

Chaque fichier a **une seule responsabilité**.
Exemple simple : si tu veux changer l'adresse email, tu touches uniquement `config.py`.

---

## 3. config.py — Le fichier de configuration

```python
ENTSOE_TOKEN   = "cbe182ef-..."   # clé pour accéder à l'API des prix électricité
EMAIL_SENDER   = "jaberhajji2005@gmail.com"
EMAIL_PASSWORD = "ekfaxwefhwfojebx"  # mot de passe d'application Gmail (pas le vrai)
COUNTRY_CODE   = "BE"             # Belgique
```

**Rôle :** Centraliser tous les identifiants en un seul endroit.
Les autres fichiers font `import config` et lisent `config.EMAIL_SENDER`, etc.

> Analogie : c'est comme un carnet d'adresses. Tous les autres fichiers consultent
> ce carnet plutôt que d'avoir les coordonnées recopiées partout.

---

## 4. database.py — La base de données

### Qu'est-ce que SQLite ?

SQLite est une base de données stockée dans **un seul fichier** (`voodoo.db`) sur le disque.
Pas besoin de serveur, tout est intégré dans Python.

### Les 5 tables

| Table                | Ce qu'elle stocke                              |
|----------------------|------------------------------------------------|
| `machines`           | Pétrin, Four tunnel, etc. + puissance + opérateur |
| `products`           | Pain blanc, Baguette, etc.                     |
| `tasks`              | Les étapes : "Pain blanc → Pétrin (20 min)"    |
| `orders`             | Les commandes du jour : "Pain blanc à 06:00"   |
| `electricity_prices` | Cache des prix ENTSO-E pour éviter de re-télécharger |

### La fonction `_connexion()`

```python
def _connexion():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

À chaque fois qu'on veut lire ou écrire dans la base, on ouvre une connexion.
`PRAGMA foreign_keys = ON` active les liens entre tables :
si tu supprimes un produit, toutes ses étapes (`tasks`) sont aussi supprimées automatiquement.

### Exemple d'une fonction CRUD

```python
def ajouter_machine(name, power_w, operator_name, operator_email, fixed_cost):
    conn = _connexion()        # 1. ouvrir la connexion
    c = conn.cursor()          # 2. créer un curseur (stylo pour écrire en SQL)
    c.execute(
        "INSERT INTO machines (...) VALUES (?, ?, ?, ?, ?)",
        (name, power_w, ...)   # 3. les ? sont remplacés par les vraies valeurs
    )
    conn.commit()              # 4. valider et sauvegarder sur le disque
    new_id = c.lastrowid       # 5. récupérer l'id auto-généré
    conn.close()               # 6. fermer la connexion
    return new_id
```

> Les `?` dans les requêtes SQL servent à éviter les injections SQL.
> C'est plus sûr que d'écrire directement `"INSERT ... VALUES ('" + name + "')"`.

### La fonction `lister_etapes_produit()`

C'est la plus complexe. Elle fait une **jointure SQL** entre `tasks` et `machines` :

```sql
SELECT t.id, t.step_order, m.name, t.duration_min, t.machine_id,
       m.power_w, m.operator_name, m.operator_email, m.fixed_cost
FROM tasks t
JOIN machines m ON t.machine_id = m.id
WHERE t.product_id = ?
ORDER BY t.step_order
```

**JOIN** (inner join) signifie : "prends chaque étape et récupère les infos de sa machine. Chaque étape doit obligatoirement être liée à une machine — il n'existe pas d'étape sans machine."

Résultat pour "Pain blanc" :
```
(1, 1, "Pétrin industriel",       20, 101, 3000, "Ahmed", "ahmed@...", 5.0)
(2, 2, "Chambre de fermentation", 60, 103,  500, "Ahmed", "ahmed@...", 2.0)
(3, 3, "Four tunnel",             30, 102, 1500, "Sophie","sophie@...",20.0)
```

---

## 5. email_sender.py — L'envoi d'emails

### `envoyer_email(to_email, subject, body)`

```python
msg = MIMEMultipart()             # crée l'enveloppe du message
msg["From"]    = config.EMAIL_SENDER
msg["To"]      = to_email
msg["Subject"] = subject
msg.attach(MIMEText(body, "plain", "utf-8"))   # ajoute le texte

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()                          # active le chiffrement TLS
    server.login(EMAIL_SENDER, EMAIL_PASSWORD) # s'authentifie
    server.send_message(msg)                   # envoie
```

> Analogie : `MIMEMultipart` = l'enveloppe, `MIMEText` = la lettre à l'intérieur.
> `starttls()` = mettre la lettre dans un coffre sécurisé avant de l'envoyer.

### `construire_planning_operateur(operator_name, schedule_lines)`

Génère simplement le texte de l'email de planning :
```
Bonjour Ahmed Benali,

Voici votre planning de production pour aujourd'hui :

  - Pain blanc — Étape 1 (Pétrin industriel) : 06:00 → 06:20 (20 min)
  - Baguette   — Étape 1 (Pétrin industriel) : 08:00 → 08:15 (15 min)

Bonne journée de travail,
Voodoo Production Manager
```

---

## 6. api_entsoe.py — Les prix de l'électricité

### `recuperer_prix_journaliers(date)`

Se connecte à l'API ENTSO-E (plateforme européenne de transparence énergétique)
et récupère les prix day-ahead de la Belgique pour une journée donnée.

```python
client = EntsoePandasClient(api_key=config.ENTSOE_TOKEN)
start  = pd.Timestamp("20260330", tz="Europe/Brussels")  # minuit ce jour
end    = start + pd.Timedelta(days=1)                    # minuit le lendemain
prices = client.query_day_ahead_prices("BE", start=start, end=end)
```

Retourne un `pandas.Series` : une liste de 24 valeurs (une par heure), indexées par timestamp.
```
2026-03-30 00:00  →  85.42 €/MWh
2026-03-30 01:00  →  78.10 €/MWh
...
2026-03-30 23:00  → 112.50 €/MWh
```

### `obtenir_prix_a_instant(prices, dt)`

Prend un datetime (ex: `06:20`) et cherche le prix de l'heure correspondante :
```python
valid = prices[prices.index <= ts]  # tous les prix dont l'heure <= 06:20
return float(valid.iloc[-1])        # le dernier = le prix de 06:00
```

> Si la production commence à 06:20, le prix applicable est celui de la tranche 06:00–07:00.

---

## 7. main.py — La fenêtre principale

### Rôle

Crée la fenêtre, l'identification du responsable, et assemble les 3 onglets.

### `__init__()` — construction de la fenêtre

```python
db.creer_tables()       # crée la base si elle n'existe pas encore
self._charger_demo()    # insère des données exemple si la base est vide

# Barre en haut : Nom et Email du responsable
id_box = QGroupBox("Identification")
self.inp_manager_name  = QLineEdit()
self.inp_manager_email = QLineEdit()

# Les 3 onglets
self.prices_tab = PricesTab(get_manager_info=self._infos_responsable)
self.config_tab = ConfigTab()
self.orders_tab = OrdersTab(self.prices_tab, get_manager_info=self._infos_responsable)
```

**Pourquoi passer `get_manager_info` aux onglets ?**
Les onglets Prix et Commandes ont besoin du nom et de l'email du responsable pour
envoyer des alertes. Plutôt que de leur donner directement les valeurs (qui peuvent
changer), on leur donne une **fonction** qu'ils appelleront au moment voulu.

```python
def _infos_responsable(self):
    return (
        self.inp_manager_name.text().strip(),
        self.inp_manager_email.text().strip()
    )
```

### `_changement_onglet(index)`

Quand l'utilisateur clique sur l'onglet "Commandes" (index 2), on actualise
automatiquement la liste des produits disponibles et les commandes affichées.

### `_charger_demo()`

Au premier lancement (base de données vide), insère 4 machines et 4 produits
pour que l'application ne soit pas vide.

---

## 8. tab_configuration.py — L'onglet Configuration

Contient **3 classes** :

```
ConfigTab          ← l'onglet principal, contient deux sous-onglets
├── MachinesTab    ← gérer les machines (ajouter, modifier, supprimer)
└── ProductsTab    ← gérer les produits et leurs étapes
```

### MachinesTab

Charge son interface depuis `ui/machines_tab.ui`.
Les widgets importants (noms venant du fichier .ui) :
- `self.table`      → tableau listant toutes les machines
- `self.inp_name`   → champ texte pour le nom
- `self.inp_power`  → champ numérique pour la puissance en watts
- `self.inp_oper`   → champ texte pour l'opérateur
- `self.inp_email`  → champ texte pour l'email opérateur
- `self.inp_fixed`  → champ numérique pour le coût fixe

**Flux d'utilisation :**
1. L'utilisateur clique sur une ligne du tableau → `_sur_selection()` remplit le formulaire
2. Il modifie les champs → clique "Modifier" → `_modifier()` appelle `db.modifier_machine()`
3. La méthode `actualiser()` recharge tout le tableau depuis la base

### ProductsTab

Même principe mais en deux parties :
- À gauche : liste des produits (`list_products`)
- À droite : tableau des étapes (`table_tasks`) du produit sélectionné

Quand on clique sur un produit à gauche, `_sur_selection_produit()` appelle
`_actualiser_etapes()` qui charge les étapes depuis `db.lister_etapes_produit()`.

---

## 9. tab_prix.py — L'onglet Prix Électricité

### Les 3 classes

```
PriceWorker       ← thread séparé pour télécharger les prix (sans bloquer l'UI)
SimpleEmailWorker ← thread séparé pour envoyer un email (sans bloquer l'UI)
PricesTab         ← l'onglet lui-même
```

### Pourquoi des QThread ?

> Imagine que tu demandes à quelqu'un de chercher un livre dans une bibliothèque.
> Si tu restes planté devant lui à attendre, tu ne peux rien faire d'autre.
> Si tu lui demandes de te rappeler quand il a trouvé, tu peux continuer tes activités.
>
> `QThread` = envoyer quelqu'un chercher le livre.
> `pyqtSignal` = le signal "j'ai trouvé !" qu'il t'envoie quand c'est terminé.

```python
class PriceWorker(QThread):
    finished = pyqtSignal(object)   # signal émis quand le téléchargement est fini
    error    = pyqtSignal(str)      # signal émis si une erreur survient

    def run(self):                  # ce code s'exécute dans le thread séparé
        self.finished.emit(api_entsoe.recuperer_prix_journaliers(self.date))
```

Dans `PricesTab` :
```python
self._worker = PriceWorker(target)
self._worker.finished.connect(self._prix_charges)   # "quand c'est fini, appelle _prix_charges"
self._worker.error.connect(self._erreur_chargement) # "si erreur, appelle _erreur_chargement"
self._worker.start()                                 # démarre le thread
```

### Chargement automatique au démarrage

```python
QTimer.singleShot(100, self._chargement_auto_prix)
```

100 ms après l'affichage de l'onglet, vérifie si les prix du jour sont en cache.
- Si oui → les affiche directement (rapide, pas de réseau)
- Si non → lance `charger_prix()` qui contacte l'API ENTSO-E

### Cache dans la base de données

Les prix téléchargés sont sauvegardés dans la table `electricity_prices`.
Si l'utilisateur recharge l'application le même jour, pas besoin de re-télécharger.

### Calcul du seuil `_verifier_seuil()`

```python
threshold = self.spn_threshold.value()        # ex: 50.0 €/MWh
below = self.prices[self.prices < threshold]  # filtre les heures < 50 €/MWh
```

Si des heures dépassent le seuil, affiche une alerte ET envoie un email au responsable.

### `prix_actuels()`

Simple getter : retourne `self.prices` (le pandas.Series chargé).
Utilisé par `tab_commandes.py` pour calculer les coûts.

---

## 10. tab_commandes.py — L'onglet Commandes

### Les 3 classes

```
EmailWorker       ← thread pour envoyer les plannings à TOUS les opérateurs
SimpleEmailWorker ← thread pour envoyer UN email (confirmation ou alerte)
OrdersTab         ← l'onglet lui-même
```

### `_ajouter_commande()` — la fonction centrale

**Étape 1 : récupérer les infos**
```python
product_id = self.cmb_product.currentData()           # id du produit sélectionné
start_time = self.time_start.time().toString("HH:mm") # ex: "06:00"
order_date = self.date_order.date().toString("yyyy-MM-dd")
tasks      = db.lister_etapes_produit(product_id)     # toutes les étapes du produit
total_min  = sum(t[3] for t in tasks)                 # durée totale en minutes
```

**Étape 2 : vérifier si ça dépasse minuit**
```python
start_dt = datetime.strptime("2026-03-30 06:00", "%Y-%m-%d %H:%M")
end_dt   = start_dt + timedelta(minutes=total_min)  # heure de fin prévue

if end_dt.date() > start_dt.date():   # fin le lendemain ?
    QMessageBox.warning(...)           # popup d'alerte
    # envoie aussi un email au responsable via SimpleEmailWorker
    return                             # n'enregistre PAS la commande
```

**Étape 3 : enregistrer et notifier**
```python
db.ajouter_commande(product_id, start_time, order_date)
self._actualiser_commandes()
# envoie email de confirmation au responsable
```

### `_calculer_couts()` — calcul du coût énergétique

Pour chaque commande dans le tableau :
```python
for task in tasks:
    duration_min = task[3]   # ex: 20 minutes
    power_w      = task[5]   # ex: 3000 watts (3 kW)
    fixed_cost   = task[8]   # ex: 5.0 € (coût fixe non-électrique)

    # Conversion : watts × heures = watt-heures → diviser par 1 000 000 = MWh
    energy_mwh = (power_w / 1_000_000) * (duration_min / 60)
    # Ex : (3000 / 1_000_000) * (20 / 60) = 0.001 MWh

    # Prix à l'instant de cette étape
    price = api_entsoe.obtenir_prix_a_instant(prices, current_dt)
    # Ex : 85.42 €/MWh

    # Coût de cette étape
    cost = energy_mwh * price + fixed_cost
    # Ex : 0.001 * 85.42 + 5.0 = 5.085 €
```

### `_envoyer_emails()` — envoi des plannings

**Étape 1 : construire les plannings par opérateur**
```python
schedules = {}   # dictionnaire : (nom_opérateur, email) → [liste de lignes]

for commande in orders:
    for etape in db.lister_etapes_produit(p_id):
        # chaque étape a forcément une machine avec un opérateur
        key  = (op_name, op_email)
        line = "Pain blanc — Étape 1 (Pétrin) : 06:00 → 06:20 (20 min)"
        schedules.setdefault(key, []).append(line)
```

Résultat :
```python
{
  ("Ahmed Benali", "ahmed@voodoo.be"): ["Pain blanc — Étape 1 ...", "Baguette — Étape 1 ..."],
  ("Sophie Dupont", "sophie@voodoo.be"): ["Pain blanc — Étape 3 ...", ...]
}
```

**Étape 2 : lancer l'envoi dans un thread**
```python
self._email_worker = EmailWorker(schedules, order_date)
self._email_worker.finished.connect(self._emails_envoyes)
self._email_worker.start()
```

`EmailWorker.run()` parcourt le dictionnaire et appelle `email_sender.envoyer_email()`
pour chaque opérateur.

---

## 11. Les fichiers .ui — Qt Designer

Les fichiers dans le dossier `ui/` (`orders_tab.ui`, `machines_tab.ui`, etc.) sont
des fichiers **XML** qui décrivent l'interface graphique visuellement.

```xml
<widget class="QPushButton" name="btn_add_order">
    <property name="text">
        <string>Ajouter la commande</string>
    </property>
</widget>
```

Ils sont chargés en Python avec :
```python
uic.loadUi(os.path.join(_UI_DIR, "orders_tab.ui"), self)
```

Cette ligne lit le fichier XML et crée automatiquement tous les widgets.
Après cette ligne, `self.btn_add_order` existe et peut être utilisé.

> **Règle importante :** le `name` dans le fichier .ui doit correspondre exactement
> au nom utilisé dans le code Python. Ex : `name="btn_add_order"` → `self.btn_add_order`.

---

## 12. Flux complet d'une commande — exemple concret

**Scénario : l'utilisateur ajoute "Pain blanc" à 06:00 le 30/03/2026**

```
1. [tab_commandes.py] _ajouter_commande()
   → lit product_id=1, start_time="06:00", order_date="2026-03-30"
   → db.lister_etapes_produit(1) retourne 4 étapes, total = 120 min
   → end_dt = 08:00 → pas de dépassement de minuit ✓
   → db.ajouter_commande(1, "06:00", "2026-03-30") → insère dans orders
   → SimpleEmailWorker envoie un email de confirmation au responsable

2. [tab_commandes.py] _calculer_couts()
   → récupère self._prices_tab.prix_actuels() (le pandas.Series de tab_prix.py)
   → pour chaque étape :
      Pétrin      (3000W, 20min) → 0.001 MWh × 85.42€ + 5€  = 5.085€
      Fermentation (500W, 60min) → 0.0005 MWh × 78€   + 2€  = 2.039€
      Four       (1500W, 30min) → 0.0125 MWh × 78€   + 20€  = 20.975€  ← prix de 06:20
      Trancheuse  (800W, 10min) → 0.00133 MWh × 81€  + 3€  = 3.108€
   → total commande = 31.207€
   → affiche dans le tableau et met à jour lbl_total

3. [tab_commandes.py] _envoyer_emails()
   → construit le planning de chaque opérateur
   → EmailWorker envoie un email à ahmed@voodoo.be, sophie@voodoo.be, marc@voodoo.be
```

---

## 13. Résumé des relations entre fichiers

```
main.py
  ├── importe database.py        → crée les tables, charge les démos
  ├── instancie ConfigTab        → tab_configuration.py
  ├── instancie PricesTab        → tab_prix.py
  └── instancie OrdersTab        → tab_commandes.py
         ├── utilise PricesTab   → pour récupérer les prix (prix_actuels())
         ├── utilise database.py → lister, ajouter, supprimer commandes/étapes
         ├── utilise api_entsoe  → obtenir_prix_a_instant()
         └── utilise email_sender→ envoyer_email(), construire_planning_operateur()

tab_prix.py
  ├── utilise api_entsoe.py      → recuperer_prix_journaliers()
  ├── utilise database.py        → charger/sauvegarder les prix en cache
  └── utilise email_sender.py   → alertes seuil au responsable

tab_configuration.py
  └── utilise database.py        → CRUD machines, produits, étapes
```

---

## 14. Mots-clés à retenir pour expliquer le code

| Terme           | Explication simple                                                   |
|-----------------|----------------------------------------------------------------------|
| **SQLite**      | Base de données dans un fichier, intégrée à Python                  |
| **CRUD**        | Create / Read / Update / Delete — les 4 opérations de base          |
| **QThread**     | Exécute du code en parallèle pour ne pas bloquer la fenêtre         |
| **pyqtSignal**  | Message envoyé quand un thread a terminé son travail                 |
| **uic.loadUi**  | Charge un fichier .ui (Qt Designer) et crée les widgets automatiquement |
| **pandas.Series** | Liste de valeurs avec un index temporel (utilisé pour les prix)  |
| **ENTSO-E**     | API européenne qui fournit les prix de l'électricité heure par heure |
| **SMTP/TLS**    | Protocole sécurisé pour envoyer des emails (port 587 pour Gmail)    |
| **JOIN**        | Requête SQL qui combine deux tables — les deux côtés doivent exister |
| **MIMEMultipart** | Structure d'un email (enveloppe + contenu)                        |
