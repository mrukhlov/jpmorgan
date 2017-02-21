#!/usr/bin/env python

import os
import datetime
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json

from flask import (
	Flask,
	request,
	make_response,
	jsonify
)

app = Flask(__name__)
log = app.logger

def parameters_extractor(params):
	dicts = [params]
	values = []

	while len(dicts):
		d = dicts.pop()

		for value in d.values():
			if isinstance(value, dict):
				dicts.append(value)
			elif isinstance(value, basestring) and len(value) > 0:
				values.append(unicode(value))

	return values

def gsheets_auth():
	print 'auth in progress'
	with open('account.json', 'r') as data_file:
		json_key = json.loads(data_file.read())
	scope = ['https://spreadsheets.google.com/feeds']
	credentials = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
	gc = gspread.authorize(credentials)
	sh = gc.open_by_key('1i8tJ_1XUwgsz0BymuK5b3c0q6a0MTw9605z2x2UabcQ')
	return sh

def sheets_get(spradsheet):
	accounts = spradsheet.worksheet("Accounts")
	transactions = spradsheet.worksheet("Transactions")
	response = spradsheet.worksheet("Response List")
	response_all = response.get_all_values()
	response_dict = dict(zip([i[0] for i in response_all],[i[1].split('/') if i[1].find('/') > -1 else i[1] for i in response_all]))
	return accounts, transactions, response_dict

sh = gsheets_auth()

@app.route('/webhook', methods=['POST'])
def webhook():
	req = request.get_json(silent=True, force=True)
	try:
		action = req.get("result").get('action')
	except AttributeError:
		return "No action, sorry."

	date_period_parameter = False

	if req['result']['parameters'].has_key('date') and len(req['result']['parameters']['date']) > 0:
		try:
			if req['result']['parameters'].has_key('date'):
				req['result']['parameters']['date'] = datetime.datetime.strptime(req['result']['parameters']['date'], '%Y-%m-%d').strftime('%B %-d, %Y')
				date_period_parameter = False
		except AttributeError:
			res = {
				"speech": 'wrong parameters',
				"displayText": 'wrong parameters',
			}
			return make_response(jsonify(res))
	elif req['result']['parameters'].has_key('date-period') and len(req['result']['parameters']['date-period']) > 0:
		try:
			if req['result']['parameters'].has_key('date-period'):
				date_p = req['result']['parameters']['date-period'].split('/')
				req['result']['parameters']['date-period'] = []
				for x in date_p:
					if datetime.datetime.strptime(x,'%Y-%m-%d').month == datetime.datetime.today().month or datetime.datetime.strptime(x, '%Y-%m-%d').month < datetime.datetime.today().month:
						req['result']['parameters']['date-period'].append(
							datetime.date(datetime.datetime.today().year,
							              datetime.datetime.strptime(x, '%Y-%m-%d').month,
							              datetime.datetime.strptime(x, '%Y-%m-%d').day).strftime('%B %d, %Y')
						)
					elif datetime.datetime.strptime(x, '%Y-%m-%d').month > datetime.datetime.today().month:
						req['result']['parameters']['date-period'].append(
							datetime.date(datetime.datetime.today().year-1,
							              datetime.datetime.strptime(x, '%Y-%m-%d').month,
							              datetime.datetime.strptime(x, '%Y-%m-%d').day).strftime('%B %d, %Y')
						)
					else:
						try:
							req['result']['parameters']['date-period'].append(
									datetime.datetime.strptime(x, '%Y-%m-%d').strftime('%B %-d, %Y')
							)
						except ValueError:
							req['result']['parameters']['date-period'].append(
									datetime.datetime.strptime(x, '%Y-%m-%d').strftime('%B %d, %Y')
							)
				date_period_parameter = True
				# print req['result']['parameters']['date-period']
		except AttributeError:
			res = {
				"speech": 'wrong parameters',
				"displayText": 'wrong parameters',
			}
	else:
		req['result']['parameters']['date-period'] = []
		start = datetime.date(datetime.datetime.today().year, datetime.datetime.today().month, 1)
		months_31 = [1, 3, 5, 7, 8, 10, 12]
		months_30 = [4, 6, 9, 11]
		if datetime.datetime.today() in months_31:
			end = datetime.date(datetime.datetime.today().year, datetime.datetime.today().month, 31)
		elif datetime.datetime.today() in months_30:
			end = datetime.date(datetime.datetime.today().year, datetime.datetime.today().month, 30)
		else:
			end = datetime.date(datetime.datetime.today().year, datetime.datetime.today().month, 28)
		try:
			req['result']['parameters']['date-period'].append(start.strftime('%B %-d, %Y'))
			req['result']['parameters']['date-period'].append(end.strftime('%B %-d, %Y'))
		except ValueError:
			req['result']['parameters']['date-period'].append(start.strftime('%B %d, %Y'))
			req['result']['parameters']['date-period'].append(end.strftime('%B %d, %Y'))

	if action == 'transfer.money':
		res = transferMoney(req)
	elif action == 'account.balance.check':
		res = balanceCheck(req)
	elif action == 'payment.due_date':
		res = paymentDueDate(req)
	elif action == 'account.spending.check':
		res = spendingCheck(req, date_period_parameter)
	elif action == 'account.earning.check':
		res = earningCheck(req, date_period_parameter)
	elif action == 'transfer.date.check':
		res = transferDateCheck(req)
	elif action == 'transfer.amount.check':
		res = transferAmountCheck(req)
	elif action == 'transfer.sender.check':
		res = transferSenderCheck(req)
	else:
		log.error("Unexpeted action.")

	return make_response(jsonify(res))

def transferMoney(req):

	accounts, transactions, response_dict = sheets_get(sh)
	contexts = req['result']['contexts']
	parameters = contexts[0]['parameters']
	action = req['result']['action']

	if isinstance(parameters['amount'], unicode) or isinstance(parameters['amount'], str) or isinstance(parameters['amount'], int) or isinstance(parameters['amount'], float):
		amount = parameters['amount']
	else:
		amount = parameters['amount']['amount']

	account_from = parameters['account-from']
	account_to = parameters['account-to']

	account_from_cell = accounts.find(account_from)
	account_to_cell = accounts.find(account_to)

	amount_from = accounts.cell(account_from_cell.row, account_from_cell.col + 1).value
	amount_to = accounts.cell(account_to_cell.row, account_to_cell.col + 1).value

	accounts.update_cell(account_from_cell.row, account_from_cell.col + 1 , float(amount_from.replace(',', '')) - float(amount))
	accounts.update_cell(account_to_cell.row, account_to_cell.col + 1 , float(amount_to.replace(',', '')) + float(amount))

	contexts = {}
	# response = 'The transfer is in progress.'
	response = response_dict[action]

	return {
		"speech": response,
		"displayText": response,
		# "contextOut": [contexts]
	}

def balanceCheck(req):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	action = req['result']['action']

	account = parameters['account']
	account_cell = accounts.find(account)
	amount = accounts.cell(account_cell.row, account_cell.col + 1).value
	if amount.find('.00') > -1:
		amount = str(int(float(amount.replace(',', ''))))

	response = response_dict[action].replace('@account', account).replace('@balance', '$'+amount)

	return {
		"speech": response,
		"displayText": response,
		# "contextOut": [contexts]
	}

def paymentDueDate(req):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	action = req['result']['action']

	account = parameters['account']
	account_cell = accounts.find(account)
	due_date = accounts.cell(account_cell.row, account_cell.col + 2).value

	response = response_dict[action].replace('@date', due_date)

	return {
		"speech": response,
		"displayText": response,
	}

def spendingCheck(req, date_period_parameter):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	action = req['result']['action']

	merch = parameters.get('merchant')
	cat = parameters.get('category')
	date = parameters.get('date')

	try:
		if date_period_parameter == False:
			parameters_list = parameters_extractor(parameters)
			response_list = sum([float(x[0].replace(',', '')) for x in filter(lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None, transactions.get_all_values()) if x[0].find('-') > -1])
		else:
			date_period = parameters['date-period']
			time_period_matched_list = filter(lambda x: x if len(x[3]) > 0 and datetime.datetime.strptime(date_period[0], '%B %d, %Y') <= datetime.datetime.strptime(x[3], '%B %d, %Y') <= datetime.datetime.strptime(date_period[1], '%B %d, %Y') else None, transactions.get_all_values()[1:])
			print time_period_matched_list
			del parameters['date-period']
			parameters_list = parameters_extractor(parameters)
			response_list = sum([float(x[0].replace(',', '')) for x in filter(lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None, time_period_matched_list) if x[0].find('-') > -1])
			# date_str = datetime.datetime.strptime(time_period_matched_list[0], '%B %d, %Y').month

		# if isinstance(response_list, list):
		# 	response = '$' + str(response_list[0]).replace('-', '')
		# else:
		# 	response = '$' + str(response_list).replace('-', '')


		if response_list == 0:
			if merch:
				# response = 'There were no transactions at %s.' % (merch)
				response = response_dict[action][2].replace('@var', merch)
			elif cat:
				# response = 'There were no transactions on %s.' % (cat)
				response = response_dict[action][2].replace('@var', cat)
			else:
				# response = 'There were no transactions.'
				response = response_dict[action][2].replace(' at @var', '')
		else:
			if merch:
				if isinstance(response_list, list):
					# response = 'You spent %s at %s.' % ('$' + str(response_list[0]).replace('-', ''), merch)
					response = response_dict[action][0].replace('@amount', '$' + str(response_list[0]).replace('-', '')).replace('@var', merch)
				else:
					# response = 'You spent %s at %s.' % ('$' + str(response_list).replace('-', ''), merch)
					response = response_dict[action][0].replace('@amount', '$' + str(response_list).replace('-', '')).replace('@var', merch)
			elif cat:
				if isinstance(response_list, list):
					# response = 'You spent %s on %s.' % ('$' + str(response_list[0]).replace('-', ''), cat)
					response = response_dict[action][0].replace('@amount', '$' + str(response_list[0]).replace('-', '')).replace('@var', cat)
				else:
					# response = 'You spent %s on %s.' % ('$' + str(response_list).replace('-', ''), cat)
					response = response_dict[action][0].replace('@amount', '$' + str(response_list).replace('-', '')).replace('@var', cat)
			else:
				if isinstance(response_list, list):
					# response = 'You spent $' + str(response_list[0]).replace('-', '')
					response = response_dict[action][1].replace('@amount', str(response_list[0]).replace('-', ''))
				else:
					# response = 'You spent $' + str(response_list).replace('-', '')
					response = response_dict[action][1].replace('@amount', str(response_list).replace('-', ''))

	except TypeError:
		response = response_dict['results.not.found']

	return {
		"speech": response,
		"displayText": response,
	}

def earningCheck(req, date_period_parameter):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	action = req['result']['action']

	try:
		if date_period_parameter == False:
			parameters_list = parameters_extractor(parameters)
			response_list = sum([float(x[0].replace(',', '')) for x in filter(lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None, transactions.get_all_values()) if x[0].find('-') == -1])
		else:
			date_period = parameters['date-period']
			time_period_matched_list = filter(lambda x: x if len(x[3]) > 0 and datetime.datetime.strptime(date_period[0], '%B %d, %Y') <= datetime.datetime.strptime(x[3], '%B %d, %Y') <= datetime.datetime.strptime(date_period[1], '%B %d, %Y') else None, transactions.get_all_values()[1:])
			del parameters['date-period']
			parameters_list = parameters_extractor(parameters)
			response_list = sum([float(x[0].replace(',', '')) for x in filter(lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None, time_period_matched_list) if x[0].find('-') == -1])
		if isinstance(response_list, list):
			# response = '$' + str(response_list[0])
			response = response_dict[action].replace('@amount', '$' + str(response_list[0]))
		else:
			# response = '$' + str(response_list)
			response = response_dict[action].replace('@amount', '$' + str(response_list))
	except TypeError:
		response = response_dict['results.not.found']

	if response_list == 0:
		response = response_dict['results.not.found']

	return {
		"speech": response,
		"displayText": response,
	}

def transferDateCheck(req):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	context = req['result']['contexts']
	action = req['result']['action']

	type = parameters.get('type')

	print parameters

	if type:
		parameters_list = parameters_extractor(parameters)
		response_list = [x[3] for x in filter(
			lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None,
			transactions.get_all_values())]
		if len(response_list) > 1:
			response_list_prsed = [datetime.datetime.strptime(i, '%B %d, %Y').strftime('%Y-%m-%d') for i in response_list]
			date = datetime.datetime.strptime(sorted(response_list_prsed)[len(response_list_prsed)-1], '%Y-%m-%d').strftime('%B %d, %Y')
			# response = 'It was %s.' % date
			response = response_dict[action].replace('@date', date)
		elif len(response_list) == 1:
			date = response_list[0]
			# response = 'It was %s.' % date
			response = response_dict[action].replace('@date', date)
		else:
			response = response_dict['results.not.found']
	else:
		response = 'Specify type.'

	if date:
		for cont in context:
			if cont['name'] == 'transfer-amount':
				cont['parameters']['date'] = date

	print context

	return {
		"speech": response,
		"displayText": response,
		"contextOut": context
	}

def transferAmountCheck(req):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	context = req['result']['contexts']
	action = req['result']['action']

	date = None
	amount = None
	type = parameters.get('type')

	for cont in context:
		if cont['name'] == 'transfer-amount':
			date = cont['parameters'].get('date')

	if date:
		parameters['date'] = date
		parameters_list = parameters_extractor(parameters)
		response_list = sum([float(x[0].replace(',', '')) for x in filter(lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None, transactions.get_all_values()) if x[0].find('-') == -1])
		# print response_list
		response = 'It was $%s.' % response_list
	elif type:
		parameters_list = parameters_extractor(parameters)
		response_list = [x[0] for x in filter(
			lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None,
			transactions.get_all_values())]
		if len(response_list) > 1:
			response_list_prsed = [datetime.datetime.strptime(i, '%B %d, %Y').strftime('%Y-%m-%d') for i in response_list]
			date = datetime.datetime.strptime(sorted(response_list_prsed)[len(response_list_prsed)-1], '%Y-%m-%d').strftime('%B %d, %Y')
			# response = 'It was $%s.' % response_list[0]
			response = response_dict[action].replace('@amount', response_list[0])
		elif len(response_list) == 1:
			date = response_list[0]
			# response = 'It was $%s.' % response_list[0]
			response = response_dict[action].replace('@amount', response_list[0])
		else:
			response = response_dict['results.not.found']
	else:
		response = 'Specify type.'

	# response = 'It was $%s.' % response_list

	if response_list:
		for cont in context:
			if cont['name'] == 'transfer-amount':
				cont['parameters']['amount'] = response_list

	return {
		"speech": response,
		"displayText": response,
		"contextOut": context
	}

def transferSenderCheck(req):

	accounts, transactions, response_dict = sheets_get(sh)
	parameters = req['result']['parameters']
	context = req['result']['contexts']
	action = req['result']['action']

	date = None
	amount = None
	type = parameters.get('type')

	for cont in context:
		if cont['name'] == 'transfer-amount':
			date = cont['parameters'].get('date')
			amount = cont['parameters'].get('amount')

	if date and amount:
		parameters['date'] = date
		parameters['amount'] = amount
		parameters_list = parameters_extractor(parameters)
		response_list = [x[2] for x in filter(
			lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None,
			transactions.get_all_values())]

		if response_list:
			# response = 'It was from %s' % response_list[0]
			response = response_dict[action].replace('@sender', response_list[0])
		else:
			response = response_dict['results.not.found']
	elif type:
		parameters_list = parameters_extractor(parameters)
		response_list = [x[2] for x in filter(
			lambda x: x if len(parameters_list) == len(set(x).intersection(set(parameters_list))) else None,
			transactions.get_all_values())]
		if len(response_list) > 1:
			response_list_prsed = [datetime.datetime.strptime(i, '%B %d, %Y').strftime('%Y-%m-%d') for i in response_list]
			date = datetime.datetime.strptime(sorted(response_list_prsed)[len(response_list_prsed)-1], '%Y-%m-%d').strftime('%B %d, %Y')
			# response = 'It was from %s.' % response_list[0]
			response = response_dict[action].replace('@sender', response_list[0])
		elif len(response_list) == 1:
			date = response_list[0]
			# response = 'It was from %s.' % response_list[0]
			response = response_dict[action].replace('@sender', response_list[0])
		else:
			response = response_dict['results.not.found']
	else:
		response = 'Specify type.'

	return {
		"speech": response,
		"displayText": response
	}

@app.route('/test', methods=['GET'])
def test():
	return 'jpmorgan Test is done!'


if __name__ == '__main__':
	port = int(os.getenv('PORT', 5000))

	app.run(
		debug=True,
		port=port,
		host='0.0.0.0'
	)
