import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from bson.errors import InvalidId
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

mongo = PyMongo(app)

# Helper functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_user_session():
    """Validate user session and return user_id if valid"""
    if 'user_id' not in session:
        return None
    
    try:
        return ObjectId(session['user_id'])
    except (InvalidId, TypeError):
        session.clear()
        return None

# Routes
@app.route('/')
def index():
    try:
        featured_products = list(mongo.db.products.find().limit(8))
        top_farmers = list(mongo.db.users.find({'user_type': 'farmer'}).limit(4))
        return render_template('index.html', 
                            featured_products=featured_products,
                            top_farmers=top_farmers)
    except Exception as e:
        app.logger.error(f"Error loading index: {str(e)}")
        flash('Error loading page', 'error')
        return render_template('index.html', featured_products=[], top_farmers=[])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        form_data = request.form.to_dict()
        
        # Validate required fields
        required_fields = ['name', 'email', 'password', 'user_type']
        if not all(field in form_data for field in required_fields) or 'profile_picture' not in request.files:
            flash('Please fill all required fields including profile picture', 'error')
            return redirect(url_for('register'))

        try:
            # Handle file upload (mandatory)
            file = request.files['profile_picture']
            if file.filename == '':
                flash('Profile picture is required', 'error')
                return redirect(url_for('register'))
                
            if not allowed_file(file.filename):
                flash('Only JPG, PNG files are allowed', 'error')
                return redirect(url_for('register'))

            # Create upload directory if not exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
            filename = f"user_{timestamp}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Save file
            file.save(filepath)
            os.chmod(filepath, 0o644)
            
            # Store relative path
            form_data['image_url'] = f"uploads/{filename}"
            
            # Hash password and create user
            form_data['password'] = generate_password_hash(form_data['password'])
            form_data['created_at'] = datetime.utcnow()
            
            # Handle farmer-specific fields
            if form_data['user_type'] == 'farmer':
                form_data['farm_name'] = form_data.get('farm_name', '')
                form_data['location'] = {
                    'address': form_data.get('address', ''),
                    'city': form_data.get('city', ''),
                    'state': form_data.get('state', ''),
                    'zipcode': form_data.get('zipcode', '')
                }
            
            # Insert user
            mongo.db.users.insert_one(form_data)
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            app.logger.error(f"Registration error: {str(e)}")
            flash('Account creation failed. Please try again.', 'error')
            return redirect(url_for('register'))
    
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please enter both email and password', 'error')
            return redirect(url_for('login'))
        
        try:
            user = mongo.db.users.find_one({'email': email})
            if user and check_password_hash(user['password'], password):
                session['user_id'] = str(user['_id'])
                session['user_type'] = user['user_type']
                session['name'] = user.get('name', 'User')
                
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            
            flash('Invalid email or password', 'error')
        
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('Login failed. Please try again.', 'error')
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    user_id = validate_user_session()
    if not user_id:
        flash('Please login to access dashboard', 'warning')
        return redirect(url_for('login'))
    
    try:
        if session['user_type'] == 'farmer':
            products = list(mongo.db.products.find({'farmer_id': user_id}))
            orders = list(mongo.db.orders.find({'farmer_id': user_id}))
            return render_template('farmers/dashboard.html', products=products, orders=orders)
        else:
            orders = list(mongo.db.orders.find({'customer_id': user_id}))
            return render_template('customers/dashboard.html', orders=orders)
    except Exception as e:
        app.logger.error(f"Dashboard error: {str(e)}")
        flash('Error loading dashboard', 'error')
        return redirect(url_for('index'))

@app.route('/products')
def product_list():
    category = request.args.get('category')
    query = {}
    if category:
        query['category'] = category
    
    try:
        products = list(mongo.db.products.find(query))
        return render_template('products/list.html', products=products)
    except Exception as e:
        app.logger.error(f"Product list error: {str(e)}")
        flash('Error loading products', 'error')
        return render_template('products/list.html', products=[])

@app.route('/products/<product_id>')
def product_detail(product_id):
    try:
        product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('product_list'))
        
        farmer = mongo.db.users.find_one({'_id': product['farmer_id']})
        return render_template('products/detail.html', product=product, farmer=farmer)
    except (InvalidId, TypeError):
        flash('Invalid product ID', 'error')
        return redirect(url_for('product_list'))
    except Exception as e:
        app.logger.error(f"Product detail error: {str(e)}")
        flash('Error loading product', 'error')
        return redirect(url_for('product_list'))

@app.route('/products/new', methods=['GET', 'POST'])
def add_product():
    user_id = validate_user_session()
    if not user_id or session.get('user_type') != 'farmer':
        flash('Please login as a farmer to add products', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Validate form data
        required_fields = ['name', 'category', 'price', 'quantity', 'description']
        if not all(field in request.form for field in required_fields):
            flash('Please fill all required fields', 'error')
            return redirect(request.url)
        
        try:
            form_data = {
                'name': request.form['name'],
                'category': request.form['category'],
                'price': float(request.form['price']),
                'quantity': int(request.form['quantity']),
                'description': request.form['description'],
                'farmer_id': user_id,
                'created_at': datetime.utcnow(),
                'is_organic': 'is_organic' in request.form
            }
        except (ValueError, KeyError) as e:
            flash('Invalid price or quantity', 'error')
            return redirect(request.url)
        
        # Process file upload
        if 'image' not in request.files:
            flash('No file was submitted', 'error')
            return redirect(request.url)
            
        file = request.files['image']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            try:
                # Create unique filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                original_filename = secure_filename(file.filename)
                filename = f"{timestamp}_{original_filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Save file
                file.save(filepath)
                
                # Set permissions
                os.chmod(filepath, 0o644)
                
                # Store URL
                form_data['image_url'] = url_for('static', filename=f'uploads/{filename}')
                
                # Save to database
                mongo.db.products.insert_one(form_data)
                flash('Product added successfully!', 'success')
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                app.logger.error(f"File upload error: {str(e)}")
                flash('Error saving product image', 'error')
                return redirect(request.url)
        else:
            flash('Allowed file types: png, jpg, jpeg, gif', 'error')
            return redirect(request.url)

    return render_template('products/create.html')

@app.route('/update_profile', methods=['POST'])
def update_profile():
    user_id = validate_user_session()
    if not user_id:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))

    try:
        update_data = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'phone': request.form.get('phone'),
            'description': request.form.get('description')
        }

        if session.get('user_type') == 'farmer':
            update_data.update({
                'farm_name': request.form.get('farm_name'),
                'location': {
                    'address': request.form.get('address'),
                    'city': request.form.get('city'),
                    'state': request.form.get('state'),
                    'zipcode': request.form.get('zipcode')
                }
            })

        # Remove None values
        update_data = {k: v for k, v in update_data.items() if v is not None}

        mongo.db.users.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        app.logger.error(f"Profile update error: {str(e)}")
        flash('Failed to update profile', 'error')
    
    return redirect(url_for('profile'))

@app.route('/update_profile_picture', methods=['POST'])
def update_profile_picture():
    user_id = validate_user_session()
    if not user_id:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))

    if 'profile_picture' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('profile'))

    file = request.files['profile_picture']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('profile'))

    if not allowed_file(file.filename):
        flash('Allowed file types: png, jpg, jpeg, gif', 'error')
        return redirect(url_for('profile'))

    try:
        # Ensure upload directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
        filename = f"profile_{user_id}_{timestamp}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save file with proper permissions
        file.save(filepath)
        os.chmod(filepath, 0o644)
        
        # Store relative path in database (without 'static/')
        image_url = f"uploads/{filename}"
        
        # Update database
        result = mongo.db.users.update_one(
            {'_id': user_id},
            {'$set': {'image_url': image_url}}
        )
        
        # Verify the update was successful
        if result.modified_count == 1:
            flash('Profile picture updated successfully!', 'success')
        else:
            flash('Failed to update profile picture', 'error')
            
    except Exception as e:
        app.logger.error(f"Error updating profile picture: {str(e)}")
        flash('Error updating profile picture', 'error')
    
    return redirect(url_for('profile'))

@app.route('/update_social_links', methods=['POST'])
def update_social_links():
    user_id = validate_user_session()
    if not user_id:
        return redirect(url_for('login'))

    try:
        social_links = {
            'facebook': request.form.get('facebook'),
            'twitter': request.form.get('twitter'),
            'instagram': request.form.get('instagram'),
            'youtube': request.form.get('youtube')
        }

        # Remove empty values
        social_links = {k: v for k, v in social_links.items() if v}
        
        mongo.db.users.update_one(
            {'_id': user_id},
            {'$set': {'social_links': social_links}}
        )
        flash('Social links updated!', 'success')
    except Exception as e:
        app.logger.error(f"Social links error: {str(e)}")
        flash('Failed to update social links', 'error')
    
    return redirect(url_for('profile'))

@app.route('/change_password', methods=['POST'])
def change_password():
    user_id = validate_user_session()
    if not user_id:
        return redirect(url_for('login'))

    try:
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('profile'))

        user = mongo.db.users.find_one({'_id': user_id})
        if not user or not check_password_hash(user['password'], current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('profile'))

        mongo.db.users.update_one(
            {'_id': user_id},
            {'$set': {'password': generate_password_hash(new_password)}}
        )
        flash('Password updated successfully!', 'success')
    except Exception as e:
        app.logger.error(f"Password change error: {str(e)}")
        flash('Failed to change password', 'error')
    
    return redirect(url_for('profile'))


@app.route('/profile')
def profile():
    try:
        user_id = validate_user_session()
        if not user_id:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        
        user = mongo.db.users.find_one(
            {'_id': user_id},
            {
                'name': 1,
                'email': 1,
                'phone': 1,
                'farm_name': 1,
                'location': 1,
                'image_url': 1,
                'social_links': 1,
                'description': 1,
                'user_type': 1
            }
        )
        
        if not user:
            session.clear()
            flash('Account not found', 'error')
            return redirect(url_for('register'))
        
        # Convert ObjectId to string
        user['_id'] = str(user['_id'])
        
        # Set safe defaults
        user.setdefault('location', {
            'address': '',
            'city': '',
            'state': '',
            'zipcode': ''
        })
        user.setdefault('social_links', {})
        user.setdefault('description', '')
        
        # Handle profile image
        if not user.get('image_url'):
            default_key = 'farmer' if user.get('user_type') == 'farmer' else 'profile'
            user['image_url'] = app.config['DEFAULT_IMAGES'][default_key]
        else:
            # Check if the uploaded image exists
            image_path = os.path.join(app.static_folder, user['image_url'])
            if not os.path.exists(image_path):
                default_key = 'farmer' if user.get('user_type') == 'farmer' else 'profile'
                user['image_url'] = app.config['DEFAULT_IMAGES'][default_key]
        
        template = 'farmers/profile.html' if user.get('user_type') == 'farmer' else 'customers/profile.html'
        return render_template(template, user=user)
        
    except Exception as e:
        app.logger.error(f"Profile error: {str(e)}", exc_info=True)
        flash('Failed to load profile. Please try again.', 'error')
        return redirect(url_for('dashboard'))
     
if __name__ == '__main__':
    # Create required directories
    required_dirs = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.static_folder, 'images')
    ]
    
    for directory in required_dirs:
        os.makedirs(directory, exist_ok=True)
        os.chmod(directory, 0o755)
    
    # Create default images if they don't exist
    for image_type, image_path in app.config['DEFAULT_IMAGES'].items():
        full_path = os.path.join(app.static_folder, image_path)
        if not os.path.exists(full_path):
            try:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    # Create minimal PNG file
                    if image_path.endswith('.png'):
                        f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82')
                    # Create minimal JPG file
                    elif image_path.endswith('.jpg') or image_path.endswith('.jpeg'):
                        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf\xff\xd9')
                os.chmod(full_path, 0o644)
            except Exception as e:
                app.logger.error(f"Error creating default image {image_path}: {str(e)}")
    
    app.run(debug=app.config.get('DEBUG', False))