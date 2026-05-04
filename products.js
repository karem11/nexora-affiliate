const PRODUCTS = [
  {
    id: 1,
    title: "Pet Water Fountain – Automatic Cat & Dog Water Dispenser",
    category: "pets",
    badge: "hot",
    image: "https://images-na.ssl-images-amazon.com/images/I/71Q3sCEBMKL._AC_SL1500_.jpg",
    stars: "★★★★★",
    rating: "4.8",
    reviews: "12,847",
    affiliateLink: "https://amzn.to/4teaa0I=kareemelsay0a-20"
  },
  {
    id: 2,
    title: "Slow Feeder Dog Bowl – Anti-Bloat Puzzle Bowl for Dogs",
    category: "pets",
    badge: "new",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE2L._AC_SL1500_.jpg",
    stars: "★★★★☆",
    rating: "4.6",
    reviews: "8,234",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE2?tag=kareemelsay0a-20"
  },
  {
    id: 3,
    title: "GPS Dog Tracker – Real-Time Location AirTag Pet Collar",
    category: "pets",
    badge: "hot",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE3L._AC_SL1500_.jpg",
    stars: "★★★★★",
    rating: "4.7",
    reviews: "5,621",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE3?tag=kareemelsay0a-20"
  },
  {
    id: 4,
    title: "LED Face Mask – Red Light Therapy Skin Rejuvenation Device",
    category: "beauty",
    badge: "hot",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE4L._AC_SL1500_.jpg",
    stars: "★★★★★",
    rating: "4.5",
    reviews: "9,102",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE4?tag=kareemelsay0a-20"
  },
  {
    id: 5,
    title: "Jade Roller & Gua Sha Set – Face Massager Skincare Tool",
    category: "beauty",
    badge: "new",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE5L._AC_SL1500_.jpg",
    stars: "★★★★☆",
    rating: "4.4",
    reviews: "23,456",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE5?tag=kareemelsay0a-20"
  },
  {
    id: 6,
    title: "Desk Organizer Set – Bamboo Desktop Storage with Drawers",
    category: "home",
    badge: "",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE6L._AC_SL1500_.jpg",
    stars: "★★★★★",
    rating: "4.9",
    reviews: "7,890",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE6?tag=kareemelsay0a-20"
  },
  {
    id: 7,
    title: "Magnetic Cable Organizer – Under Desk Cable Management",
    category: "tech",
    badge: "new",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE7L._AC_SL1500_.jpg",
    stars: "★★★★☆",
    rating: "4.3",
    reviews: "4,567",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE7?tag=kareemelsay0a-20"
  },
  {
    id: 8,
    title: "Lick Mat for Dogs & Cats – Slow Feeder Anxiety Relief",
    category: "pets",
    badge: "",
    image: "https://images-na.ssl-images-amazon.com/images/I/71EXAMPLE8L._AC_SL1500_.jpg",
    stars: "★★★★★",
    rating: "4.7",
    reviews: "31,200",
    affiliateLink: "https://www.amazon.com/dp/B08EXAMPLE8?tag=kareemelsay0a-20"
  }
];

function renderProducts(filter) {
  const grid = document.getElementById('productsGrid');
  if (!grid) return;
  const list = filter ? PRODUCTS.filter(p => p.category === filter) : PRODUCTS;
  if (list.length === 0) {
    grid.innerHTML = '<p style="color:var(--text2);text-align:center;grid-column:1/-1;padding:40px">No products found in this category yet. Check back soon!</p>';
    return;
  }
  grid.innerHTML = list.map(p => `
    <div class="product-card">
      <div class="product-img-wrap">
        ${p.badge ? `<span class="product-badge ${p.badge}">${p.badge.toUpperCase()}</span>` : ''}
        <img src="${p.image}" alt="${p.title}" loading="lazy" onerror="this.src='https://via.placeholder.com/300x200/16161f/6c63ff?text=NEXORA'" />
      </div>
      <div class="product-body">
        <span class="product-cat">${p.category}</span>
        <p class="product-title">${p.title}</p>
        <div class="product-stars">
          <span class="stars">${p.stars}</span>
          <span class="rating-count">(${p.reviews})</span>
        </div>
      </div>
      <div class="product-footer">
        <div>
          <div class="product-price">Check Price</div>
          <div class="price-note">on Amazon →</div>
        </div>
        <a href="${p.affiliateLink}" target="_blank" rel="noopener noreferrer" class="btn-amazon">🛒 View Deal</a>
      </div>
    </div>
  `).join('');
}

document.addEventListener('DOMContentLoaded', function() {
  const params = new URLSearchParams(window.location.search);
  const cat = params.get('cat');
  renderProducts(cat || null);
});
