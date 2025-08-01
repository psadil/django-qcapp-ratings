// Define the controller function outside DOMContentLoaded to allow re-initialization
const initializeCanvasController = () => {
    const canvas = document.getElementById('canvas');
    const canvasWrapper = document.querySelector('.canvas-wrapper');

    // If canvas doesn't exist yet, wait for next animation frame and try again
    if (!canvas) {
        requestAnimationFrame(initializeCanvasController);
        return;
    }

    const ctx = canvas.getContext('2d');
    const img = new Image();

    // Array to store click coordinates
    const clickPoints = [];

    // Function to resize canvas while maintaining aspect ratio
    const resizeCanvas = () => {
        if (!img.complete || !canvasWrapper) return;

        const wrapperWidth = canvasWrapper.clientWidth;
        const imgAspectRatio = img.width / img.height;

        // Calculate new dimensions maintaining aspect ratio
        let newWidth = wrapperWidth;
        let newHeight = wrapperWidth / imgAspectRatio;

        // Set canvas display size (CSS)
        canvas.style.width = newWidth + 'px';
        canvas.style.height = newHeight + 'px';

        // Set canvas internal size (for drawing)
        canvas.width = img.width;
        canvas.height = img.height;

        // Redraw after resize
        drawImageAndPoints();
    };

    // Function to load the image from the current base64 data
    const loadImage = () => {
        img.src = document.getElementById('image-data')?.value;
    };

    // Set up the image load handler
    img.onload = () => {
        // Initial resize and draw
        resizeCanvas();
    };

    const drawImageAndPoints = () => {
        // Ensure canvas context exists
        if (!ctx) return;

        // Clear canvas and redraw image
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);

        // Draw gold circles at all clicked points
        ctx.strokeStyle = 'gold';
        ctx.lineWidth = 2;

        clickPoints.forEach(point => {
            ctx.beginPath();
            ctx.arc(point.x, point.y, 10, 0, 2 * Math.PI);
            ctx.stroke();
        });
    };

    // Check if a click is inside any existing circle
    const findClickedCircle = (x, y) => {
        const radius = 10;
        return clickPoints.findIndex(point => {
            const distance = Math.sqrt((x - point.x) ** 2 + (y - point.y) ** 2);
            return distance <= radius;
        });
    };

    // Convert screen coordinates to canvas coordinates
    const screenToCanvasCoords = (screenX, screenY) => {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;

        return {
            x: (screenX - rect.left) * scaleX,
            y: (screenY - rect.top) * scaleY
        };
    };

    // Handle clicks on canvas
    const handleCanvasClick = e => {
        // Convert screen coordinates to canvas coordinates
        const canvasCoords = screenToCanvasCoords(e.clientX, e.clientY);

        // Check if user clicked on an existing circle
        const circleIndex = findClickedCircle(canvasCoords.x, canvasCoords.y);

        if (circleIndex !== -1) {
            // Remove the circle if clicked
            clickPoints.splice(circleIndex, 1);
        } else {
            // Add new point
            clickPoints.push({ x: canvasCoords.x, y: canvasCoords.y });
        }

        // Redraw image with updated points
        drawImageAndPoints();
    };

    // Handle window resize
    const handleResize = () => {
        resizeCanvas();
    };

    // Attach event listeners
    canvas.addEventListener('click', handleCanvasClick);
    window.addEventListener('resize', handleResize);

    // Handle submit button click
    document.getElementById('submit').addEventListener('click', () => {
        // Prepare data for submission
        const data = {
            points: JSON.stringify(clickPoints)
        };
        document.getElementById('form').setAttribute('hx-vals', JSON.stringify(data));
    });

    // Initial image load
    loadImage();

    // Return an object with cleanup method for when component is destroyed
    return {
        cleanup: () => {
            if (canvas) {
                canvas.removeEventListener('click', handleCanvasClick);
            }
            window.removeEventListener('resize', handleResize);
        }
    };
};

// Let's track our controller instance
// let canvasController = null;

// Initialize the controller when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    canvasController = initializeCanvasController();

    // Listen for HTMX events globally
    document.body.addEventListener('htmx:afterSettle', () => {
        // Clean up old controller if it exists
        if (canvasController?.cleanup) {
            canvasController.cleanup();
        }

        // Initialize a new controller after DOM updates
        canvasController = initializeCanvasController();
    });

    document.addEventListener('keydown', function (e) {
        // Ignore if typing in a textarea or input
        if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

        const key = e.key.toLowerCase();
        if (key === 'enter') {
            form.requestSubmit ? form.requestSubmit() : form.submit();
            e.preventDefault();
        }
    });

});
