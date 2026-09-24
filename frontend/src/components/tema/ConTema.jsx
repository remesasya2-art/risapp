/**
 * ConTema — pone la marca del modo oscuro alrededor de una pantalla entera.
 *
 * POR QUE EN LA RUTA Y NO EN LA PANTALLA
 *
 *   Varias pantallas devuelven raíces distintas según el estado —cargando,
 *   error, cada paso de un flujo—, y la marca tiene que estar en todas. Una
 *   que se olvide queda clara en medio de la app oscura, y nadie se entera
 *   hasta que la ve alguien con el modo oscuro puesto. En la ruta se pone una
 *   vez y cubre todos los estados.
 *
 * POR QUE `display: contents`
 *
 *   La caja no existe para el diseño —no ocupa lugar, no cambia un margen ni
 *   un `flex`—, pero sigue en el árbol, y las variables de CSS y
 *   `color-scheme` se heredan por el árbol. Es exactamente lo que hace falta:
 *   la marca sin tocar nada de cómo se ve la pantalla.
 */
export default function ConTema({ children }) {
  return (
    <div className="con-tema" style={{ display: 'contents' }}>
      {children}
    </div>
  );
}
