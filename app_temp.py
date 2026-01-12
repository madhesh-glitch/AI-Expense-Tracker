@app.route('/expenses/add', methods=['POST'])
@login_required
def add_expense_manual():
    try:
        payload = request.get_json(silent=True) or {}
        category = (payload.get('category') or 'Misc').strip() or 'Misc'
        amount = float(payload.get('amount') or 0)
        merchant = (payload.get('merchant') or '').strip()
        note = (payload.get('note') or '').strip()
        
        # Handle date formatting
        date_input = payload.get('date')
        if date_input:
            if 'T' in date_input:  # Handle datetime-local input format
                date_str = date_input.replace('T', ' ')
            else:
                date_str = date_input
        else:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        date_str = date_str.strip()

        # For analysis helpers, build a simple text blob
        text_blob = "\n".join(filter(None, [merchant, note, f"Category: {category}"]))
        assessment, reason, tips = assess_expense(category, amount, text_blob)

        doc = {
            'user': current_user.email,
            'filename': None,
            'category': category,
            'amount': amount,
            'text': text_blob,
            'date': date_str,
            'merchant': merchant,
            'note': note,
            'created_at': datetime.now()
        }
        
        # Insert the document and get the inserted ID
        result = expenses_col.insert_one(doc)
        
        if not result.inserted_id:
            raise Exception("Failed to insert expense")

        # Get updated category totals
        pipeline = [
            {"$match": {"user": current_user.email}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]
        grouped = list(expenses_col.aggregate(pipeline))

        return jsonify({
            'success': True,
            'message': 'Expense added successfully',
            'data': grouped,
            'assessment': {
                'label': assessment,
                'reason': reason,
                'category': category,
                'amount': amount,
                'tips': TIP_BANK.get(category, tips)
            }
        })
    except Exception as e:
        print('❌ add_expense_manual error:', str(e))
        return jsonify({
            'success': False,
            'error': str(e) or 'Failed to add expense'
        }), 500
