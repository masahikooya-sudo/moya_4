if (new URLSearchParams(window.location.search).get("error") === "forbidden") {
  document.getElementById("login-error").style.display = "block";
}
