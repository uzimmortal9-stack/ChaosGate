const items = ["Field jacket", "Travel kettle", "Carbon bottle"];
const root = document.getElementById("items");
if (root) {
  root.innerHTML = items.map((name) => `<li>${name}</li>`).join("");
}
