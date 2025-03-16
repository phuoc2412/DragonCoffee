
from app import app, db
from models import Category, Product
import random

def seed_menu():
    with app.app_context():
        # Xóa dữ liệu cũ
        Product.query.delete()
        Category.query.delete()
        
        # Tạo các danh mục
        categories = [
            {"name": "Cà phê", "description": "Các loại cà phê đặc trưng"},
            {"name": "Trà", "description": "Các loại trà thơm ngon"},
            {"name": "Sinh tố", "description": "Sinh tố từ trái cây tươi"},
            {"name": "Nước ép", "description": "Nước ép trái cây tự nhiên"},
            {"name": "Bánh ngọt", "description": "Các loại bánh tươi ngon"},
            {"name": "Đồ ăn nhẹ", "description": "Snacks và đồ ăn vặt"},
            {"name": "Đá xay", "description": "Đồ uống đá xay mát lạnh"},
            {"name": "Đồ uống đặc biệt", "description": "Thức uống độc đáo của quán"}
        ]
        
        db_categories = []
        for cat in categories:
            category = Category(name=cat["name"], description=cat["description"])
            db.session.add(category)
            db_categories.append(category)
        
        # Commit để lấy ID của categories
        db.session.commit()
        
        # Dữ liệu sản phẩm mẫu
        coffee_names = ["Cà phê đen", "Cà phê sữa", "Cappuccino", "Latte", "Americano", "Espresso", "Mocha", 
                       "Cà phê trứng", "Cà phê dừa", "Cà phê caramel", "Cold Brew", "Cà phê Ireland"]
                       
        tea_names = ["Trà sen", "Trà đào", "Trà vải", "Trà chanh", "Trà gừng", "Trà sữa trân châu",
                    "Trà ô long", "Trà đen", "Trà xanh", "Hồng trà", "Trà hoa cúc", "Trà cam quế"]
                    
        smoothie_names = ["Sinh tố xoài", "Sinh tố dâu", "Sinh tố bơ", "Sinh tố chuối", "Sinh tố việt quất",
                         "Sinh tố dừa", "Sinh tố kiwi", "Sinh tố chanh dây", "Sinh tố sapoche"]
                         
        juice_names = ["Nước ép cam", "Nước ép táo", "Nước ép dưa hấu", "Nước ép cà rốt", "Nước ép dứa",
                      "Nước ép nho", "Nước ép ổi", "Nước ép cần tây", "Nước ép củ dền"]
                      
        pastry_names = ["Bánh tiramisu", "Bánh phô mai", "Bánh socola", "Bánh red velvet", "Bánh matcha",
                       "Bánh cupcake", "Bánh croissant", "Bánh Danish", "Bánh cookie"]
                       
        snack_names = ["Khoai tây chiên", "Bánh mì nướng bơ tỏi", "Mì Ý", "Sandwich", "Khoai lang chiên",
                      "Xúc xích nướng", "Bánh mì chảo", "Nachos", "Cánh gà chiên"]
                      
        frappe_names = ["Chocolate đá xay", "Matcha đá xay", "Caramel đá xay", "Vanilla đá xay",
                       "Oreo đá xay", "Dâu đá xay", "Coffee đá xay", "Mint đá xay"]
                       
        special_names = ["Dragon Special Coffee", "Trà hoa hồng", "Trà sữa than tre", "Cà phê dừa nhiệt đới",
                        "Smoothie cầu vồng", "Trà hoa quả nhiệt đới", "Cocktail trái cây"]

        all_products = {
            0: coffee_names,
            1: tea_names,
            2: smoothie_names,
            3: juice_names,
            4: pastry_names,
            5: snack_names,
            6: frappe_names,
            7: special_names
        }

        # Tạo sản phẩm cho từng danh mục
        for cat_index, names in all_products.items():
            category = db_categories[cat_index]
            for name in names:
                price = round(random.uniform(25, 85), 3)
                product = Product(
                    name=name,
                    description=f"Thức uống/món ăn {name.lower()} thơm ngon đặc trưng của Dragon Coffee",
                    price=price,
                    image_url=f"https://source.unsplash.com/400x300/?{name.replace(' ', '+')}",
                    is_available=True,
                    is_featured=random.choice([True, False]),
                    category_id=category.id
                )
                db.session.add(product)
        
        db.session.commit()
        print("Đã thêm dữ liệu mẫu thành công!")

if __name__ == "__main__":
    seed_menu()
