"""Verde Financeiro: aplicativo financeiro local para navegador."""
import csv
import io
import os
import secrets
import sqlite3
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from calendar import monthrange
from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for, send_file

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
DATA_DIR = Path(os.environ.get('VERDE_DATA_DIR', str(Path.home() / '.verde_financeiro')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'web.db'
KEY_FILE = DATA_DIR / '.web_secret'
if not KEY_FILE.exists():
    KEY_FILE.write_text(secrets.token_hex(32), encoding='utf-8')
    try: KEY_FILE.chmod(0o600)
    except OSError: pass
app.secret_key = KEY_FILE.read_text(encoding='utf-8')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

DEFAULT_CATEGORIES = {
    'receita': ['Salário', 'Freelance', 'Vendas', 'Rendimentos', 'Presentes', 'Outras receitas'],
    'despesa': ['Alimentação', 'Transporte', 'Moradia', 'Saúde', 'Educação', 'Lazer', 'Assinaturas', 'Compras pessoais', 'Contas e serviços', 'Outros'],
}

def db():
    connection = sqlite3.connect(DB, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('receita','despesa')), active INTEGER NOT NULL DEFAULT 1, UNIQUE(name,kind));
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, description TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), kind TEXT NOT NULL CHECK(kind IN ('receita','despesa')), category_id INTEGER REFERENCES categories(id) ON DELETE RESTRICT, day TEXT NOT NULL, method TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, name TEXT NOT NULL, target INTEGER NOT NULL CHECK(target>0), saved INTEGER NOT NULL DEFAULT 0 CHECK(saved>=0), deadline TEXT, description TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY, name TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), due TEXT NOT NULL, category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL, frequency TEXT NOT NULL DEFAULT 'única', paid INTEGER NOT NULL DEFAULT 0 CHECK(paid IN (0,1)));
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        for kind, names in DEFAULT_CATEGORIES.items():
            for name in names:
                c.execute('INSERT OR IGNORE INTO categories(name,kind) VALUES(?,?)', (name, kind))
        for key, value in [('nickname',''), ('opening_balance','0'), ('hide_values','0'), ('currency','BRL')]:
            c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (key,value))
        # Migração não destrutiva para bancos de versões anteriores.
        def columns(table): return {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
        for table, newcols in {
            'categories': {'active':'INTEGER NOT NULL DEFAULT 1'},
            'transactions': {'method':"TEXT NOT NULL DEFAULT ''", 'notes':"TEXT NOT NULL DEFAULT ''"},
            'goals': {'deadline':'TEXT', 'description':"TEXT NOT NULL DEFAULT ''"},
            'bills': {'category_id':'INTEGER REFERENCES categories(id) ON DELETE SET NULL', 'frequency':"TEXT NOT NULL DEFAULT 'única'"},
        }.items():
            existing = columns(table)
            for column, definition in newcols.items():
                if column not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

def parse_money(raw, *, allow_zero=False):
    text = str(raw or '').strip().replace('R$', '').replace(' ', '').replace('\u00a0', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        number = Decimal(text)
        if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
            raise ValueError()
        if number > Decimal('9999999999.99') or number.as_tuple().exponent < -2:
            raise ValueError()
        return int((number * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Digite um valor válido, por exemplo 125,90.') from None

def money(value):
    amount = int(value or 0)
    prefix = '-' if amount < 0 else ''
    return prefix + 'R$ ' + f'{abs(amount)/100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

def shortdate(value):
    if not value: return 'Sem prazo'
    try: return date.fromisoformat(value).strftime('%d/%m/%Y')
    except ValueError: return value

app.jinja_env.filters['money'] = money
app.jinja_env.filters['shortdate'] = shortdate

@app.before_request
def csrf_protection():
    if 'csrf_token' not in session: session['csrf_token'] = secrets.token_hex(24)
    if request.method == 'POST' and not app.config.get('TESTING'):
        if not secrets.compare_digest(request.form.get('csrf_token',''), session['csrf_token']):
            abort(400, description='Formulário expirado. Atualize a página e tente novamente.')

@app.context_processor
def shared():
    return {'csrf_token': session.get('csrf_token',''), 'today': date.today().isoformat(), 'year':date.today().year}

def checked_date(value, optional=False):
    if optional and not value: return None
    try: return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError): raise ValueError('Informe uma data válida.') from None

def positive_id(value):
    try:
        ident = int(value)
        if ident <= 0: raise ValueError()
        return ident
    except (TypeError, ValueError): raise ValueError('Identificador inválido.') from None

def period_bounds(selection, start='', end=''):
    today = date.today()
    if selection == 'anterior':
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1).isoformat(), last.isoformat()
    if selection == '30dias': return (today-timedelta(days=29)).isoformat(), today.isoformat()
    if selection == 'ano': return today.replace(month=1,day=1).isoformat(), today.isoformat()
    if selection == 'personalizado':
        a,b = checked_date(start),checked_date(end)
        if a>b: raise ValueError('A data inicial deve ser anterior à data final.')
        return a,b
    if selection == 'todos': return '0001-01-01', '9999-12-31'
    first=today.replace(day=1)
    last=today.replace(day=monthrange(today.year,today.month)[1])
    return first.isoformat(),last.isoformat()

def tx_query(c, params):
    clauses=[]; args=[]
    q=(params.get('q') or '').strip()
    if q:
        clauses.append('(LOWER(t.description) LIKE ? OR LOWER(t.notes) LIKE ?)')
        args += [f'%{q.lower()}%',f'%{q.lower()}%']
    kind=params.get('kind','')
    if kind in ('receita','despesa'): clauses.append('t.kind=?');args.append(kind)
    cat=params.get('category','')
    if cat:
        clauses.append('t.category_id=?');args.append(positive_id(cat))
    period=params.get('period','todos')
    if period!='todos':
        a,b=period_bounds(period,params.get('start',''),params.get('end',''))
        clauses.append('t.day BETWEEN ? AND ?');args.extend([a,b])
    sort={'recentes':'t.day DESC,t.id DESC','antigas':'t.day ASC,t.id ASC','maior':'t.amount DESC,t.id DESC','menor':'t.amount ASC,t.id ASC'}.get(params.get('sort','recentes'),'t.day DESC,t.id DESC')
    sql='SELECT t.*,c.name AS category FROM transactions t LEFT JOIN categories c ON c.id=t.category_id'
    if clauses: sql+=' WHERE '+' AND '.join(clauses)
    return c.execute(sql+' ORDER BY '+sort,args).fetchall()

def destination(page):
    return redirect(url_for('home',page=page))

def form_error(page, func):
    try: func()
    except (ValueError,sqlite3.IntegrityError,sqlite3.OperationalError) as exc:
        flash(str(exc),'error')
    return destination(page)

@app.get('/')
def home():
    page=request.args.get('page','inicio')
    allowed={'inicio','movimentacoes','categorias','relatorios','metas','contas','configuracoes'}
    if page not in allowed: page='inicio'
    selection=request.args.get('period','mes')
    try: start,end=period_bounds(selection,request.args.get('start',''),request.args.get('end',''))
    except ValueError as exc:
        flash(str(exc),'error'); selection='mes';start,end=period_bounds('mes')
    with db() as c:
        settings={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}
        cats=[dict(r) for r in c.execute('SELECT * FROM categories ORDER BY kind,name')]
        all_tx=[dict(r) for r in c.execute('SELECT t.*,c.name category FROM transactions t LEFT JOIN categories c ON c.id=t.category_id ORDER BY t.day DESC,t.id DESC')]
        goals=[dict(r) for r in c.execute('SELECT * FROM goals ORDER BY id DESC')]
        bills=[dict(r) for r in c.execute('SELECT b.*,c.name category FROM bills b LEFT JOIN categories c ON c.id=b.category_id ORDER BY b.paid,b.due')]
        try: visible=[dict(r) for r in tx_query(c,request.args)] if page=='movimentacoes' else []
        except ValueError as exc: flash(str(exc),'error');visible=[]
    in_period=[t for t in all_tx if start<=t['day']<=end]
    income=sum(t['amount'] for t in in_period if t['kind']=='receita')
    expense=sum(t['amount'] for t in in_period if t['kind']=='despesa')
    balance=int(settings.get('opening_balance','0'))+sum(t['amount']*(1 if t['kind']=='receita' else -1) for t in all_tx if t['day']<=date.today().isoformat())
    bycat={}
    for t in in_period:
        if t['kind']=='despesa':
            label=t['category'] or 'Sem categoria'
            bycat[label]=bycat.get(label,0)+t['amount']
    bycat=sorted(bycat.items(),key=lambda item:-item[1])
    months=[]
    for i in range(5,-1,-1):
        y=date.today().year; m=date.today().month-i
        while m<=0: m+=12;y-=1
        prefix=f'{y}-{m:02d}'
        txs=[t for t in all_tx if t['day'].startswith(prefix)]
        months.append({'label':f'{m:02d}/{str(y)[2:]}','income':sum(t['amount'] for t in txs if t['kind']=='receita'),'expense':sum(t['amount'] for t in txs if t['kind']=='despesa')})
    maxmonth=max([m['income'] for m in months]+[m['expense'] for m in months]+[1])
    for m in months:
        m['ipct']=round(m['income']/maxmonth*100)
        m['epct']=round(m['expense']/maxmonth*100)
    prevstart,prevend=period_bounds('anterior')
    prevtx=[t for t in all_tx if prevstart<=t['day']<=prevend]
    prevresult=sum(t['amount']*(1 if t['kind']=='receita' else -1) for t in prevtx)
    return render_template('index.html',page=page,settings=settings,categories=cats,transactions=all_tx,visible=visible,goals=goals,bills=bills,period=selection,start=start,end=end,income=income,expense=expense,result=income-expense,balance=balance,bycat=bycat,months=months,previous_result=prevresult, total_tx=len(all_tx),today_date=date.today())

@app.post('/movimentacao/salvar')
def save_transaction():
    def action():
        kind=request.form.get('kind','');desc=request.form.get('description','').strip()
        if kind not in ('receita','despesa') or not desc or len(desc)>120: raise ValueError('Informe uma descrição de até 120 caracteres e um tipo válido.')
        amount=parse_money(request.form.get('amount'));day=checked_date(request.form.get('day'))
        category=positive_id(request.form.get('category_id'))
        method=request.form.get('method','').strip()[:60];notes=request.form.get('notes','').strip()[:500]
        with db() as c:
            if not c.execute('SELECT 1 FROM categories WHERE id=? AND kind=?',(category,kind)).fetchone(): raise ValueError('Selecione uma categoria compatível com o tipo.')
            ident=request.form.get('id','').strip()
            if ident:
                cur=c.execute('UPDATE transactions SET kind=?,description=?,amount=?,day=?,category_id=?,method=?,notes=? WHERE id=?',(kind,desc,amount,day,category,method,notes,positive_id(ident)))
                if not cur.rowcount: raise ValueError('Movimentação não encontrada.')
            else:
                c.execute('INSERT INTO transactions(kind,description,amount,day,category_id,method,notes) VALUES(?,?,?,?,?,?,?)',(kind,desc,amount,day,category,method,notes))
        flash('Movimentação salva com sucesso.','ok')
    return form_error('movimentacoes',action)

@app.post('/movimentacao/<int:ident>/excluir')
def delete_transaction(ident):
    def action():
        with db() as c: c.execute('DELETE FROM transactions WHERE id=?',(ident,))
        flash('Movimentação excluída.','ok')
    return form_error('movimentacoes',action)

@app.post('/categoria/salvar')
def save_category():
    def action():
        name=request.form.get('name','').strip();kind=request.form.get('kind','')
        if not name or len(name)>60 or kind not in ('receita','despesa'): raise ValueError('Informe nome e tipo válidos.')
        with db() as c:
            ident=request.form.get('id','')
            if ident:
                old=c.execute('SELECT * FROM categories WHERE id=?',(positive_id(ident),)).fetchone()
                if not old: raise ValueError('Categoria não encontrada.')
                if old['kind']!=kind and c.execute('SELECT 1 FROM transactions WHERE category_id=? LIMIT 1',(int(ident),)).fetchone(): raise ValueError('Não é possível mudar o tipo de uma categoria em uso.')
                c.execute('UPDATE categories SET name=?,kind=?,active=1 WHERE id=?',(name,kind,int(ident)))
            else:c.execute('INSERT INTO categories(name,kind) VALUES(?,?)',(name,kind))
        flash('Categoria salva.','ok')
    return form_error('categorias',action)

@app.post('/categoria/<int:ident>/alternar')
def toggle_category(ident):
    def action():
        with db() as c:
            row=c.execute('SELECT active FROM categories WHERE id=?',(ident,)).fetchone()
            if not row: raise ValueError('Categoria não encontrada.')
            c.execute('UPDATE categories SET active=? WHERE id=?',(0 if row['active'] else 1,ident))
        flash('Categoria atualizada. Os registros antigos foram preservados.','ok')
    return form_error('categorias',action)

@app.post('/meta/salvar')
def save_goal():
    def action():
        name=request.form.get('name','').strip()
        if not name or len(name)>100: raise ValueError('Informe o nome da meta.')
        target=parse_money(request.form.get('target'))
        saved=parse_money(request.form.get('saved') or '0',allow_zero=True)
        deadline=checked_date(request.form.get('deadline'),optional=True)
        description=request.form.get('description','').strip()[:300]
        with db() as c:
            ident=request.form.get('id','')
            if ident:
                c.execute('UPDATE goals SET name=?,target=?,saved=?,deadline=?,description=? WHERE id=?',(name,target,saved,deadline,description,positive_id(ident)))
            else:c.execute('INSERT INTO goals(name,target,saved,deadline,description) VALUES(?,?,?,?,?)',(name,target,saved,deadline,description))
        flash('Meta salva. O valor guardado é informado por você e não altera o saldo automaticamente.','ok')
    return form_error('metas',action)

@app.post('/meta/<int:ident>/aporte')
def goal_deposit(ident):
    def action():
        amount=parse_money(request.form.get('amount'))
        with db() as c:
            cur=c.execute('UPDATE goals SET saved=saved+? WHERE id=?',(amount,ident))
            if not cur.rowcount: raise ValueError('Meta não encontrada.')
        flash('Aporte registrado na meta. Para refletir no saldo, registre também a movimentação correspondente.','ok')
    return form_error('metas',action)

@app.post('/meta/<int:ident>/excluir')
def goal_delete(ident):
    def action():
        with db() as c:c.execute('DELETE FROM goals WHERE id=?',(ident,))
        flash('Meta excluída.','ok')
    return form_error('metas',action)

@app.post('/conta/salvar')
def save_bill():
    def action():
        name=request.form.get('name','').strip()
        if not name or len(name)>100:raise ValueError('Informe o nome da conta.')
        amount=parse_money(request.form.get('amount'));due=checked_date(request.form.get('due'))
        frequency=request.form.get('frequency','única')
        if frequency not in ('única','semanal','mensal','anual'):raise ValueError('Periodicidade inválida.')
        cat=request.form.get('category_id') or None
        with db() as c:
            if cat and not c.execute("SELECT 1 FROM categories WHERE id=? AND kind='despesa'",(positive_id(cat),)).fetchone():raise ValueError('Categoria de despesa inválida.')
            ident=request.form.get('id','')
            if ident:c.execute('UPDATE bills SET name=?,amount=?,due=?,frequency=?,category_id=? WHERE id=?',(name,amount,due,frequency,cat,positive_id(ident)))
            else:c.execute('INSERT INTO bills(name,amount,due,frequency,category_id) VALUES(?,?,?,?,?)',(name,amount,due,frequency,cat))
        flash('Conta prevista salva. Não é lançada como despesa automaticamente.','ok')
    return form_error('contas',action)

@app.post('/conta/<int:ident>/alternar')
def bill_toggle(ident):
    def action():
        with db() as c:c.execute('UPDATE bills SET paid=1-paid WHERE id=?',(ident,))
        flash('Status da conta atualizado. Isso não cria uma movimentação financeira.','ok')
    return form_error('contas',action)

@app.post('/conta/<int:ident>/excluir')
def bill_delete(ident):
    def action():
        with db() as c:c.execute('DELETE FROM bills WHERE id=?',(ident,))
        flash('Conta excluída.','ok')
    return form_error('contas',action)

@app.post('/configuracoes')
def save_settings():
    def action():
        nickname=request.form.get('nickname','').strip()[:60]
        opening=parse_money(request.form.get('opening_balance','0').lstrip('-'),allow_zero=True)
        if request.form.get('opening_balance','0').strip().startswith('-'): opening=-opening
        hide='1' if request.form.get('hide_values')=='1' else '0'
        with db() as c:
            for key,value in [('nickname',nickname),('opening_balance',str(opening)),('hide_values',hide)]:
                c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        flash('Preferências salvas.','ok')
    return form_error('configuracoes',action)

@app.get('/exportar')
def export_csv():
    try:
        with db() as c:rows=tx_query(c,request.args)
    except ValueError as exc:
        flash(str(exc),'error');return destination('movimentacoes')
    output=io.StringIO();output.write('\ufeff');writer=csv.writer(output,delimiter=';')
    writer.writerow(['Data','Descrição','Tipo','Categoria','Valor (R$)','Forma','Observações'])
    for t in rows:writer.writerow([shortdate(t['day']),t['description'],t['kind'],t['category'] or '',f"{t['amount']/100:.2f}".replace('.',','),t['method'],t['notes']])
    return Response(output.getvalue(),content_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="verde-financeiro-{date.today().isoformat()}.csv"','Cache-Control':'no-store'})

@app.get('/backup')
def backup():
    target=io.BytesIO()
    # Backup consistente do SQLite, sem copiar um banco aberto diretamente.
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        output=Path(folder)/'verde-financeiro-backup.db'
        with db() as source, sqlite3.connect(output) as dest:source.backup(dest)
        target.write(output.read_bytes())
    target.seek(0)
    return send_file(target,as_attachment=True,download_name=f'verde-financeiro-backup-{date.today().isoformat()}.db',mimetype='application/octet-stream')

init_db()
if __name__=='__main__':
    import webbrowser
    from threading import Timer
    url='http://127.0.0.1:5000'
    print(f'Verde Financeiro: {url}')
    if os.environ.get('VERDE_NO_BROWSER')!='1':Timer(1.2,lambda:webbrowser.open(url)).start()
    app.run(host='127.0.0.1',port=5000,debug=False)
