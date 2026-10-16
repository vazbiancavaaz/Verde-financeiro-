"""Testes das regras e dos endpoints do aplicativo web."""
import os
import tempfile
import sys
import unittest
from pathlib import Path

# Banco de teste isolado: nunca toca nos dados reais do usuário.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
TEMP = tempfile.TemporaryDirectory()
os.environ['VERDE_DATA_DIR'] = TEMP.name
from app import app, db, init_db, money, parse_money, period_bounds

class FinancialRulesTests(unittest.TestCase):
    def test_money_brazilian(self):
        self.assertEqual(parse_money('1.250,50'),125050)
        self.assertEqual(money(125050),'R$ 1.250,50')
    def test_money_rejects_invalid(self):
        for value in ['abc','-20','0','12,345','NaN','Infinity']:
            with self.subTest(value=value),self.assertRaises(ValueError):parse_money(value)
    def test_zero_allowed_for_opening_balance(self):
        self.assertEqual(parse_money('0,00',allow_zero=True),0)
    def test_custom_dates(self):
        self.assertEqual(period_bounds('personalizado','2026-01-01','2026-01-31'),('2026-01-01','2026-01-31'))
        with self.assertRaises(ValueError):period_bounds('personalizado','2026-02-01','2026-01-01')

class WebTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING']=True
        self.client=app.test_client()
        with db() as c:
            c.execute('DELETE FROM transactions');c.execute('DELETE FROM goals');c.execute('DELETE FROM bills')
            c.execute("UPDATE settings SET value='0' WHERE key='opening_balance'")
    def test_all_pages_open(self):
        for page in ['inicio','movimentacoes','categorias','relatorios','metas','contas','configuracoes']:
            with self.subTest(page=page):
                response=self.client.get('/?page='+page)
                self.assertEqual(response.status_code,200)
                self.assertIn(b'verde',response.data)
    def test_persistence_and_totals(self):
        with db() as c:
            cat=c.execute("SELECT id FROM categories WHERE kind='receita' LIMIT 1").fetchone()['id']
        resp=self.client.post('/movimentacao/salvar',data={'kind':'receita','description':'Pagamento teste','amount':'125,90','day':'2026-10-10','category_id':cat})
        self.assertEqual(resp.status_code,302)
        with db() as c:
            row=c.execute("SELECT amount FROM transactions WHERE description='Pagamento teste'").fetchone()
            self.assertEqual(row['amount'],12590)
        self.assertIn(b'Pagamento teste',self.client.get('/?page=movimentacoes').data)
    def test_reject_mismatched_category(self):
        with db() as c:cat=c.execute("SELECT id FROM categories WHERE kind='despesa' LIMIT 1").fetchone()['id']
        self.client.post('/movimentacao/salvar',data={'kind':'receita','description':'Invalido','amount':'20','day':'2026-10-10','category_id':cat})
        with db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM transactions WHERE description='Invalido'").fetchone()[0],0)
    def test_export_csv(self):
        resp=self.client.get('/exportar')
        self.assertEqual(resp.status_code,200)
        self.assertIn('text/csv',resp.content_type)
    def test_backup(self):
        resp=self.client.get('/backup')
        self.assertEqual(resp.status_code,200)
        self.assertTrue(resp.data.startswith(b'SQLite format 3'))
    def test_category_deactivation_keeps_old_transactions(self):
        with db() as c:
            cat=c.execute("SELECT id FROM categories WHERE kind='despesa' LIMIT 1").fetchone()['id']
            c.execute("INSERT INTO transactions(description,amount,kind,category_id,day) VALUES('Histórico',2000,'despesa',?,'2026-10-10')",(cat,))
        self.client.post(f'/categoria/{cat}/alternar')
        with db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions WHERE category_id=?',(cat,)).fetchone()[0],1)
            self.assertEqual(c.execute('SELECT active FROM categories WHERE id=?',(cat,)).fetchone()[0],0)
            c.execute('UPDATE categories SET active=1 WHERE id=?',(cat,))
    def test_goal_deposit_does_not_change_balance(self):
        with db() as c:
            c.execute("INSERT INTO goals(name,target,saved) VALUES('Viagem',100000,0)")
            ident=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.client.post(f'/meta/{ident}/aporte',data={'amount':'100,00'})
        with db() as c:
            self.assertEqual(c.execute('SELECT saved FROM goals WHERE id=?',(ident,)).fetchone()[0],10000)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)

if __name__=='__main__':unittest.main()
